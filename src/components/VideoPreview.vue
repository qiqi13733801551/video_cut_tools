<template>
  <div class="preview-wrapper" ref="wrapperRef">
    <!-- 最终WebGL输出画布，显示给用户 -->
    <canvas
      ref="glCanvasRef"
      class="preview-canvas"
      @mousedown="handleCanvasMouseDown"
      @mousemove="handleCanvasMouseMove"
      @mouseup="handleCanvasMouseUp"
      @mouseleave="handleCanvasMouseUp"
    ></canvas>

    <div class="control-bar">
      <button @click="play">播放</button>
      <button @click="pause">暂停</button>
      <button @click="toggleMute">{{ isMute ? "取消静音" : "静音" }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted, computed } from "vue";
import { parseGIF, decompressFrames } from "gifuct-js";

const props = defineProps({
  currentTime: { type: Number, default: 0 },
  trackData: { type: Object, default: () => ({ tracks: [] }) },
  canvasWidth: { type: Number, default: 720 },
  canvasHeight: { type: Number, default: 405 }
});

const emit = defineEmits([
  "play",
  "pause",
  "clip-select",
  "clip-update",
  "timeupdate",
  "seeked"
]);

const glCanvasRef = ref(null);
const wrapperRef = ref(null);
/** 2D离屏画布：绘制所有图层，作为WebGL输入纹理 */
let offscreen2dCanvas = null;
let ctx2d = null;

let gl = null;
let animationId = null;

// ========== 增量渲染缓存核心变量（2D绘制层） ==========
let cacheCanvas = null;
let cacheCtx = null;
let dirtyRects = [];
let forceFullRender = true;
let lastRenderTime = 0;

// 转场专用两张离屏画布
let transCanvasA = null;
let transCtxA = null;
let transCanvasB = null;
let transCtxB = null;
// 标记当前是否处于转场渲染模式
let inTransitionRender = false;
let activeTransitionInfo = null; // { progress, type, clipA, clipB }


// 播放状态
const isPlaying = ref(false);
const displayTime = ref(props.currentTime);
const selectedClipId = ref(null);

// 视频资源池
const videoPool = new Map();
// 音频资源池
const audioPool = new Map();

const assetCache = new Map();
const MAX_CACHE = 30;
const gifCanvasCache = new Map();

// ========== WebAudio ==========
let audioCtx = null;
let masterGain = null;

// 拖拽状态
const dragState = ref({
  active: false,
  clip: null,
  startX: 0,
  startY: 0,
  originX: 0,
  originY: 0,
  originScale: 1,
  handleKey: null,
  mode: "move"
});

const HANDLES = [
  { key: "lt", dx: -0.5, dy: -0.5 },
  { key: "rt", dx: 0.5, dy: -0.5 },
  { key: "lb", dx: -0.5, dy: 0.5 },
  { key: "rb", dx: 0.5, dy: 0.5 }
];

const PLAY_SPEED = 1.0;
const MAX_DELTA_SEC = 0.08;
const SYNC_TOLERANCE = 0.10;
const SEEK_COOLDOWN = 500;
const MAX_SNAPSHOT_COUNT = 20;

// ========== WebGL 全局shader资源 ==========
let glTextureInput = null;
let glTextureB = null;
let glNoiseTexture = null; // 新增：dissolve静态噪声纹理
let glProgram = null;
let glVbo = null;
let uTextureLoc = null;
let uResolutionLoc = null;
let uFilterCountLoc = null;
let uFilterKeysLoc = null;
let uFilterIntensityLoc = null;
let uNoiseTexLoc = null; // 新增噪声纹理uniform位置

// 顶点着色器【修复后】
const vertexShaderSource = `#version 300 es
precision highp float;
in vec2 aPos;
out vec2 vUv;
void main(){
    vUv = aPos * 0.5 + 0.5;
    // ========= 修复：Y轴翻转，适配canvas2D上传的纹理 =========
    vUv.y = 1.0 - vUv.y;
    gl_Position = vec4(aPos,0.0,1.0);
}
`;

// 片段着色器：支持多滤镜叠加 + 开幕闭幕特效
const fragmentShaderSource = `#version 300 es
precision highp float;
uniform sampler2D uTexture;
uniform vec2 uResolution;
// ==========【新增：基础调色uniform】=========
uniform float uBrightness;
uniform float uContrast;
uniform float uSaturation;
uniform float uTemp;
uniform float uTint;
uniform float uVignette;
// 滤镜参数
uniform int uFilterCount;
uniform int uFilterKeys[8];
uniform float uFilterIntensity[8];
// =========【特效uniform 开幕闭幕 方向模糊】=========
uniform int uEffectCount;
uniform int uEffectKeys[4];
uniform float uEffectProgress[4];
uniform float uEffectIntensity[4];
// ========== 转场参数 ==========
uniform int uHasTransition;
uniform int uTransType;
uniform float uTransProgress;
uniform sampler2D uTexB; // 第二张纹理（B画面）
uniform sampler2D uNoiseTex; // dissolve静态噪声纹理
#define TRANS_NONE 0
#define TRANS_DISSOLVE 1
#define TRANS_CROSS_DISSOLVE 2
#define TRANS_DIP_BLACK 3
#define TRANS_DIP_WHITE 4
#define TRANS_WIPE_LEFT  5
#define TRANS_WIPE_RIGHT 6
in vec2 vUv;
out vec4 fragColor;
#define FILTER_NONE        0
#define FILTER_RETRO       1
#define FILTER_GRAY        2
#define FILTER_BLUE_FILM   3
#define FILTER_CLEAR       4
#define FILTER_DUSK        5
#define FILTER_SUNNY       6
#define FILTER_SEA         7
#define FILTER_OIL         8
#define FILTER_SKETCH      9
// 特效枚举
#define EFFECT_NONE        0
#define EFFECT_OPEN        1   // 开幕：中间向两边展开
#define EFFECT_CLOSE       2   // 闭幕：两边向中间收缩
#define EFFECT_BLUR_GAUSS      3   // 高斯模糊
vec3 adjustSaturation(vec3 rgb, float sat){
    float lum = dot(rgb, vec3(0.2126,0.7152,0.0722));
    return mix(vec3(lum), rgb, sat);
}
vec3 adjustBrightness(vec3 c, float b){ return c*b; }
vec3 adjustContrast(vec3 c, float co){ return ((c-0.5)*co)+0.5; }
vec3 hueRotate(vec3 color, float deg){
    float rad = radians(deg);
    float c = cos(rad);
    float s = sin(rad);
    mat3 m = mat3(
        c + (1.0-c)*0.2126, (1.0-c)*0.7152 - s*0.2126, (1.0-c)*0.0722 + s*0.2126,
        (1.0-c)*0.2126 + s*0.2126, c + (1.0-c)*0.7152, (1.0-c)*0.0722 - s*0.7152,
        (1.0-c)*0.2126 - s*0.2126, (1.0-c)*0.7152 + s*0.7152, c + (1.0-c)*0.0722
    );
    return m*color;
}
// ==========【新增调色函数】=========
// 色温：temp[-100~100] 正=暖黄，负=冷蓝
vec3 adjustTemperature(vec3 color, float temp){
    float factor = temp / 100.0;
    color.r *= (1.0 + factor * 0.15);
    color.b *= (1.0 - factor * 0.15);
    return clamp(color,0.0,1.0);
}
// 暗角 vignette 0~1
vec3 adjustVignette(vec3 color, vec2 uv, float vig){
    if(vig <= 0.0) return color;
    vec2 center = vec2(0.5);
    float dist = length(uv - center);
    float vigFactor = 1.0 - smoothstep(0.35, 0.85, dist * vig * 1.8);
    return color * vigFactor;
}
// ---------------- 新增：保留亮度的色调染色，tint范围 [-100 ~ 100] ----------------
// -100：极浅浅绿，+100：极浅浅红，0：无染色
vec3 adjustTintBalance(vec3 color, float tintValue) {
    // 两个端点颜色（进一步变浅，饱和度更低）
    const vec3 TINT_NEG = vec3(0.72, 0.92, 0.76);   // -100 更淡浅绿
    const vec3 TINT_POS = vec3(0.92, 0.72, 0.72);   // +100 更淡浅红

    float lum = dot(color, vec3(0.2126, 0.7152, 0.0722)); // 原图亮度
    float factor = tintValue / 100.0; // 映射到 -1.0 ~ +1.0

    vec3 tintColor;
    if(factor < 0.0){
        tintColor = mix(vec3(1.0), TINT_NEG, abs(factor));
    }else{
        tintColor = mix(vec3(1.0), TINT_POS, factor);
    }

    // 保留原始亮度，只取染色的色度
    vec3 colored = color * tintColor;
    float newLum = dot(colored, vec3(0.2126, 0.7152, 0.0722));
    colored = colored * (lum / max(newLum, 0.001)); // 恢复原图亮度
    return clamp(colored, 0.0, 1.0);
}


vec4 applySingleFilter(vec4 color, int key, float intensity){
    vec3 col = color.rgb;
    if(intensity < 0.01) return color;
    if(key == FILTER_RETRO){
        col = adjustSaturation(col, 1.0 + 0.20*intensity);
        col = adjustContrast(col,1.0+0.22*intensity);
        float sepiaR = dot(col,vec3(0.393,0.769,0.189));
        float sepiaG = dot(col,vec3(0.349,0.686,0.168));
        float sepiaB = dot(col,vec3(0.272,0.534,0.131));
        col = mix(col,vec3(sepiaR,sepiaG,sepiaB),0.42*intensity);
    }else if(key == FILTER_GRAY){
        float l = dot(col,vec3(0.2126,0.7152,0.0722));
        col = mix(col,vec3(l),intensity);
    }else if(key == FILTER_BLUE_FILM){
        col = adjustSaturation(col, 1.0-0.35*intensity);
        col = hueRotate(col, 210.0 * intensity);
    }else if(key == FILTER_CLEAR){
        col = adjustBrightness(col,1.0+0.18*intensity);
        col = adjustSaturation(col,1.0+0.25*intensity);
    }else if(key == FILTER_DUSK){
        col = adjustBrightness(col,1.0+0.12*intensity);
        float sepiaR = dot(col,vec3(0.393,0.769,0.189));
        float sepiaG = dot(col,vec3(0.349,0.686,0.168));
        float sepiaB = dot(col,vec3(0.272,0.534,0.131));
        col = mix(col,vec3(sepiaR,sepiaG,sepiaB),0.22*intensity);
    }else if(key == FILTER_SUNNY){
        col = adjustBrightness(col,1.0+0.25*intensity);
        col = adjustSaturation(col,1.0+0.35*intensity);
    }else if(key == FILTER_SEA){
        col = hueRotate(col,195.0*intensity);
        col = adjustSaturation(col,1.0+0.20*intensity);
    }else if(key == FILTER_OIL){
        col = adjustContrast(col,1.0+0.35*intensity);
        col = adjustSaturation(col,1.0+0.40*intensity);
    }else if(key == FILTER_SKETCH){
        float l = dot(col,vec3(0.2126,0.7152,0.0722));
        col = mix(col,vec3(l),intensity);
        col = adjustContrast(col,1.0+0.45*intensity);
    }
    return vec4(col,color.a);
}
// 5‑tap双向高斯水平模糊（对齐ffmpeg gblur水平方向）
vec4 gaussBlur(sampler2D tex, vec2 uv, float intensity, vec2 resolution){
    // 和导出端 sigma = intensity *10 做观感对齐；uv单位偏移
    float sigma = intensity * 10.0;
    float pixelOffset = sigma / resolution.x;
    vec4 c0 = texture(tex, uv);
    vec4 c1p = texture(tex, uv + vec2(pixelOffset*0.25, 0.0));
    vec4 c1n = texture(tex, uv - vec2(pixelOffset*0.25, 0.0));
    vec4 c2p = texture(tex, uv + vec2(pixelOffset*0.50, 0.0));
    vec4 c2n = texture(tex, uv - vec2(pixelOffset*0.50, 0.0));
    vec4 c3p = texture(tex, uv + vec2(pixelOffset*0.75, 0.0));
    vec4 c3n = texture(tex, uv - vec2(pixelOffset*0.75, 0.0));
    vec4 c4p = texture(tex, uv + vec2(pixelOffset*1.00, 0.0));
    vec4 c4n = texture(tex, uv - vec2(pixelOffset*1.00, 0.0));
    // 简单加权平均模拟双向高斯
    vec4 avg = (c0*6.0 + (c1p+c1n)*4.0 + (c2p+c2n)*2.0 + (c3p+c3n)*1.0 + (c4p+c4n)*0.5) / 20.0;
    return mix(c0, avg, intensity);
}
// 处理单例裁切/模糊特效
vec4 applySingleEffect(sampler2D tex, vec4 inColor, vec2 uv, int effKey, float progress, float intensity, vec2 resolution){
    vec4 outColor = inColor;
    if(intensity < 0.01) return outColor;
    float p = mix(1.0, progress, intensity);
    if(effKey == EFFECT_OPEN){
        // 开幕：中间向两边展开
        float halfW = p * 0.5;
        float left = 0.5 - halfW;
        float right = 0.5 + halfW;
        if(uv.x < left || uv.x > right){
            outColor = vec4(0.0,0.0,0.0,1.0);
        }
    }else if(effKey == EFFECT_CLOSE){
        // 闭幕：两边向中间收缩
        float halfW = (1.0 - p) * 0.5;
        float left = 0.5 - halfW;
        float right = 0.5 + halfW;
        if(uv.x < left || uv.x > right){
            outColor = vec4(0.0,0.0,0.0,1.0);
        }
    }else if(effKey == EFFECT_BLUR_GAUSS){
        // 双向水平高斯模糊，对齐ffmpeg gblur导出
        outColor = gaussBlur(tex, uv, intensity, resolution);
    }
    return outColor;
}
void main(){
    vec4 colorA = texture(uTexture, vUv);
    vec4 colorB = texture(uTexB, vUv);
    vec4 color = colorA;
    if(uHasTransition == 1){
        float p = uTransProgress;
        if(uTransType == TRANS_DISSOLVE){
            // ===== 对齐ffmpeg xfade=dissolve 静态噪声溶解，无帧间闪烁 =====
            // 8.0控制颗粒大小，和ffmpeg观感对齐
            float noise = texture(uNoiseTex, vUv * 8.0).r;
            color = (p >= noise) ? colorB : colorA;
        }else if(uTransType == TRANS_CROSS_DISSOLVE){
            // ffmpeg xfade=fade 标准交叉淡入淡出
            color = mix(colorA, colorB, p);
        }else if(uTransType == TRANS_DIP_BLACK){
            // ffmpeg dip‑to‑black：先变黑，再切B画面
            float t = 2.0 * p;
            vec4 black = vec4(0.0,0.0,0.0,1.0);
            if(t < 1.0){
                color = mix(colorA, black, t);
            }else{
                color = mix(black, colorB, t - 1.0);
            }
        }else if(uTransType == TRANS_DIP_WHITE){
            // ffmpeg dip‑to‑white：先变白，再切B画面
            float t = 2.0 * p;
            vec4 white = vec4(1.0,1.0,1.0,1.0);
            if(t < 1.0){
                color = mix(colorA, white, t);
            }else{
                color = mix(white, colorB, t - 1.0);
            }
        }else if(uTransType == TRANS_WIPE_LEFT){
            // wipe‑left：B画面从左向右划入，A被覆盖
            if(vUv.x < p){
                color = colorB;
            }else{
                color = colorA;
            }
        }
        else if(uTransType == TRANS_WIPE_RIGHT){
            // wipe‑right：B画面从右向左划入
            if(vUv.x > (1.0 - p)){
                color = colorB;
            }else{
                color = colorA;
            }
        }
    }
    // =========【新增：基础调色，转场之后，滤镜特效之前执行】=========
    vec3 c = color.rgb;
    c = adjustBrightness(c, uBrightness);
    c = adjustContrast(c, uContrast);
    c = adjustSaturation(c, uSaturation);
    c = adjustTemperature(c, uTemp);
    c = adjustTintBalance(c, uTint);
    c = adjustVignette(c, vUv, uVignette);
    color.rgb = c;
    // 2、循环执行所有特效（开幕、闭幕、横向模糊、纵向模糊）
    for(int i=0;i<4;i++){
        if(i >= uEffectCount) break;
        color = applySingleEffect(uTexture, color, vUv, uEffectKeys[i], uEffectProgress[i], uEffectIntensity[i], uResolution);
    }
    // 3、执行滤镜
    for(int i=0;i<8;i++){
        if(i >= uFilterCount) break;
        color = applySingleFilter(color, uFilterKeys[i], uFilterIntensity[i]);
    }
    fragColor = color;
}
`;





// filterKey映射到shader内部枚举id
const FILTER_SHADER_MAP = {
  "filter-film-retro": 1,
  "filter-film-gray": 2,
  "filter-film-blue": 3,
  "filter-fresh-clear":4,
  "filter-fresh-dusk":5,
  "filter-travel-sunny":6,
  "filter-travel-sea":7,
  "filter-art-oil":8,
  "filter-art-sketch":9
};

const TRANS_SHADER_MAP = {
  "dissolve": 1,
  "cross-dissolve": 2,
  "dip-to-black": 3,
  "dip-to-white": 4,
  "wipe-left":5,
  "wipe-right":6
}

// 总时长
const totalDuration = computed(() => {
  let maxT = 0;
  if (!props.trackData?.tracks) return 0;
  props.trackData.tracks.forEach(track => {
    if (track.visible === false) return;
    track.clips.forEach(clip => {
      const end = clip.endTime;
      if (end > maxT) maxT = end;
    });
  });
  return maxT;
});

function initAudioContext() {
  if (audioCtx) return;
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  masterGain = audioCtx.createGain();
  masterGain.gain.value = 1;
  masterGain.connect(audioCtx.destination);
}

function compileShader(glCtx, type, source) {
  const s = glCtx.createShader(type);
  glCtx.shaderSource(s, source);
  glCtx.compileShader(s);
  if (!glCtx.getShaderParameter(s, glCtx.COMPILE_STATUS)) {
    console.error("shader compile err", glCtx.getShaderInfoLog(s));
  }
  return s;
}

/** 初始化WebGL2环境 */
function initWebGL() {
  const canvas = glCanvasRef.value;
  canvas.width = props.canvasWidth;
  canvas.height = props.canvasHeight;
  gl = canvas.getContext("webgl2");
  if (!gl) {
    console.warn("浏览器不支持WebGL2，滤镜、特效功能关闭");
    return false;
  }
  const vs = compileShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
  const fs = compileShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);
  glProgram = gl.createProgram();
  gl.attachShader(glProgram, vs);
  gl.attachShader(glProgram, fs);
  gl.linkProgram(glProgram);
  if (!gl.getProgramParameter(glProgram, gl.LINK_STATUS)) {
    console.error("program link error", gl.getProgramInfoLog(glProgram));
    gl = null;
    return false;
  }
  // 全屏三角带
  glVbo = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, glVbo);
  const vertices = new Float32Array([
    -1,-1, 1,-1, -1,1,
    -1,1, 1,-1, 1,1
  ]);
  gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

  // uniform位置缓存
  uTextureLoc = gl.getUniformLocation(glProgram, "uTexture");
  uResolutionLoc = gl.getUniformLocation(glProgram, "uResolution");
  uFilterCountLoc = gl.getUniformLocation(glProgram, "uFilterCount");
  uFilterKeysLoc = gl.getUniformLocation(glProgram, "uFilterKeys");
  uFilterIntensityLoc = gl.getUniformLocation(glProgram, "uFilterIntensity");

  // ==========【新增缓存转场uniform位置】==========
  window.uHasTransitionLoc = gl.getUniformLocation(glProgram, "uHasTransition");
  window.uTransTypeLoc = gl.getUniformLocation(glProgram, "uTransType");
  window.uTransProgressLoc = gl.getUniformLocation(glProgram, "uTransProgress");
  window.uTexBLoc = gl.getUniformLocation(glProgram, "uTexB");
  uNoiseTexLoc = gl.getUniformLocation(glProgram, "uNoiseTex"); // 噪声贴图

  // =========【新增调色uniform位置】=========
  window.uBrightnessLoc = gl.getUniformLocation(glProgram, "uBrightness");
  window.uContrastLoc = gl.getUniformLocation(glProgram, "uContrast");
  window.uSaturationLoc = gl.getUniformLocation(glProgram, "uSaturation");
  window.uTempLoc = gl.getUniformLocation(glProgram, "uTemp");
  window.uTintLoc = gl.getUniformLocation(glProgram, "uTint");
  window.uVignetteLoc = gl.getUniformLocation(glProgram, "uVignette");


  // 创建输入纹理
  glTextureInput = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, glTextureInput);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

  glTextureB = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, glTextureB);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

  // ---------------- 生成FFmpeg dissolve 静态噪声纹理（只初始化一次）----------------
  glNoiseTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, glNoiseTexture);
  const noiseW = 256;
  const noiseH = 256;
  const noiseData = new Uint8Array(noiseW * noiseH);
  for(let i = 0; i < noiseW * noiseH; i++){
    noiseData[i] = Math.floor(Math.random() * 256);
  }
  gl.texImage2D(gl.TEXTURE_2D,0, gl.R8, noiseW, noiseH, 0, gl.RED, gl.UNSIGNED_BYTE, noiseData);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

  gl.useProgram(glProgram);
  gl.uniform1i(uTextureLoc,0);
  gl.uniform1i(window.uTexBLoc,1); // texB绑定纹理单元1
  gl.uniform1i(uNoiseTexLoc,2);   // 噪声贴图绑定纹理单元2
  return true;
}



/** 上传2D画布图像到WebGL纹理，提交滤镜参数 + 特效参数，绘制到屏幕 */
function webglRender(off2dCanvas, activeFilterClips, activeEffectClips, canvasB) {
  if(!gl || !glProgram) return;
  gl.viewport(0,0,props.canvasWidth, props.canvasHeight);

  // =========【新增：读取激活视频片段调色参数，上传shader】=========
  const activeList = getActiveClips(displayTime.value);
  const videoClipItem = activeList.find(i=>i.clip.type === 'video');
  let clipBrightness = 1.0;
  let clipContrast = 1.0;
  let clipSaturation = 1.0;
  let clipTemp = 0.0;
  let clipTint = 0.0;
  let clipVignette = 0.0;
  if(videoClipItem){
    const clip = videoClipItem.clip;
    clipBrightness = clip.brightness ?? 1.0;
    clipContrast = clip.contrast ?? 1.0;
    clipSaturation = clip.saturation ?? 1.0;
    clipTemp = clip.temp ?? 0.0;
    clipTint = clip.tint ?? 0.0;
    clipVignette = clip.vignette ?? 0.0;
  }
  gl.uniform1f(window.uBrightnessLoc, clipBrightness);
  gl.uniform1f(window.uContrastLoc, clipContrast);
  gl.uniform1f(window.uSaturationLoc, clipSaturation);
  gl.uniform1f(window.uTempLoc, clipTemp);
  gl.uniform1f(window.uTintLoc, clipTint);
  gl.uniform1f(window.uVignetteLoc, clipVignette);

  // 纹理单元0:主画面
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, glTextureInput);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE, off2dCanvas);

  // 纹理单元1：转场B画面
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, glTextureB);
  if(inTransitionRender && canvasB){
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE, canvasB);
  }

  // 纹理单元2：dissolve静态噪声贴图
  gl.activeTexture(gl.TEXTURE2);
  gl.bindTexture(gl.TEXTURE_2D, glNoiseTexture);

  gl.uniform2f(uResolutionLoc, props.canvasWidth, props.canvasHeight);

  // ---------- 滤镜参数 ----------
  const keyArr = new Int32Array(8);
  const intensityArr = new Float32Array(8);
  let filterCnt = 0;
  for(const clip of activeFilterClips){
    if(filterCnt >=8) break;
    const sid = FILTER_SHADER_MAP[clip.filterKey];
    if(sid !== undefined){
      keyArr[filterCnt] = sid;
      intensityArr[filterCnt] = clip.intensity ?? 0;
      filterCnt++;
    }
  }
  gl.uniform1i(uFilterCountLoc, filterCnt);
  gl.uniform1iv(uFilterKeysLoc, keyArr);
  gl.uniform1fv(uFilterIntensityLoc, intensityArr);

  // ============ 特效Uniform上传，最多4个特效同时生效 ============
  const EFFECT_NONE = 0
  const EFFECT_OPEN = 1
  const EFFECT_CLOSE = 2
  const EFFECT_BLUR_GAUSS = 3

  const effKeyArr = new Int32Array(4);
  const effProgressArr = new Float32Array(4);
  const effIntensityArr = new Float32Array(4);
  let effCnt = 0;

  for(const effClip of activeEffectClips){
    if(effCnt >= 4) break
    if(effClip.effectKey === 'open'){
      effKeyArr[effCnt] = EFFECT_OPEN
    }else if(effClip.effectKey === 'close'){
      effKeyArr[effCnt] = EFFECT_CLOSE
    }else if(effClip.effectKey === 'blur‑gauss'){
      effKeyArr[effCnt] = EFFECT_BLUR_GAUSS
    }else{
      effKeyArr[effCnt] = EFFECT_NONE
    }
    effProgressArr[effCnt] = effClip.progress
    effIntensityArr[effCnt] = effClip.intensity ?? 1.0
    effCnt++
  }

  const uEffectCount = gl.getUniformLocation(glProgram, "uEffectCount");
  const uEffectKeys = gl.getUniformLocation(glProgram, "uEffectKeys");
  const uEffectProgress = gl.getUniformLocation(glProgram, "uEffectProgress");
  const uEffectIntensity = gl.getUniformLocation(glProgram, "uEffectIntensity");

  gl.uniform1i(uEffectCount, effCnt);
  gl.uniform1iv(uEffectKeys, effKeyArr);
  gl.uniform1fv(uEffectProgress, effProgressArr);
  gl.uniform1fv(uEffectIntensity, effIntensityArr);

  // =========【重要！转场uniform 在draw之前设置】========
  if(inTransitionRender && activeTransitionInfo && canvasB){
    gl.uniform1i(window.uHasTransitionLoc, 1);
    gl.uniform1i(window.uTransTypeLoc, activeTransitionInfo.type);
    gl.uniform1f(window.uTransProgressLoc, activeTransitionInfo.progress);
  }else{
    gl.uniform1i(window.uHasTransitionLoc, 0);
  }

  gl.bindBuffer(gl.ARRAY_BUFFER, glVbo);
  const aPos = gl.getAttribLocation(glProgram,"aPos");
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false,0,0);

  // 所有uniform设置完成，再绘制！！
  gl.drawArrays(gl.TRIANGLES,0,6);
}



function getActiveClips(time) {
  const active = [];
  if (!props.trackData?.tracks) return active;
  props.trackData.tracks.forEach(track => {
    if (track.visible === false) return;
    track.clips.forEach(clip => {
      const s = clip.startTime;
      const e = clip.endTime;
      if (e <= s) return;
      if (time >= s && time <= e) {
        active.push({ track, clip });
      }
    });
  });
  return active;
}

function createVideoEl(clipId, src) {
  const video = document.createElement("video");
  video.style.width = "1px";
  video.style.height = "1px";
  video.style.opacity = "0";
  video.style.pointerEvents = "none";
  video.preload = "metadata";
  video.volume = 1;
  video.src = src;
  video._lastSeekMs = 0;
  document.body.appendChild(video);

  videoPool.set(clipId, {
    video,
    audioSource: null,
    clipGainNode: null, // 新增：单片段音量增益
    useNativeVolume: false
  });
  return videoPool.get(clipId);
}

function syncVideoSingle(videoInfo, clip, globalTime) {
  const { video } = videoInfo;
  const timelineOffset = globalTime - clip.startTime;
  const clipRate = clip.playbackRate ?? 1.0
  let targetInnerTime = clip.trimStart + timelineOffset / clipRate;
  targetInnerTime = Math.max(clip.trimStart, Math.min(clip.trimEnd, targetInnerTime));

  const clipTimelineEnd = clip.endTime;
  const inRange = globalTime >= clip.startTime && globalTime <= clipTimelineEnd;
  if (!inRange) {
    video.pause();
    return;
  }

  if (clip.hasSplitAudio) {
    video.muted = true;
  } else {
    video.muted = false;
  }

  video.playbackRate = 1.0
  const targetVol = clip.volume ?? 1.0;

  if (audioCtx && !videoInfo.audioSource && !videoInfo.useNativeVolume) {
    try {
      videoInfo.audioSource = audioCtx.createMediaElementSource(video);
      videoInfo.clipGainNode = audioCtx.createGain();
      videoInfo.clipGainNode.gain.value = targetVol;
      // 链路 audioSource → clipGainNode → masterGain
      videoInfo.audioSource.connect(videoInfo.clipGainNode);
      videoInfo.clipGainNode.connect(masterGain);
    } catch (err) {
      videoInfo.useNativeVolume = true;
    }
  }
  // 每帧更新音量！！拖动滑块实时生效
  if(videoInfo.clipGainNode){
    videoInfo.clipGainNode.gain.value = targetVol;
  }else if(videoInfo.useNativeVolume){
    video.volume = Math.min(targetVol, 1.0);
  }

  const diff = Math.abs(video.currentTime - targetInnerTime);
  const nowMs = performance.now();
  // =========新增readyState保护：元数据未就绪，不执行seek，等待视频加载 =========
  const videoReady = video.readyState >= 1;
  if (videoReady && diff > SYNC_TOLERANCE && nowMs - video._lastSeekMs > SEEK_COOLDOWN) {
    video.currentTime = targetInnerTime;
    video._lastSeekMs = nowMs;
  }

  if (isPlaying.value) {
    if (video.paused && videoReady) video.play().catch(() => { });
  } else {
    video.pause();
  }
}


function syncAllActiveVideos(time) {
  const activeList = getActiveClips(time);
  const activeClipIds = new Set(activeList.map(i => i.clip.id));

  for (const [cid, videoInfo] of videoPool) {
    if (!activeClipIds.has(cid)) {
      videoInfo.video.pause();
    }
  }

  activeList.forEach(({ clip }) => {
    if (clip.type === "audio" || clip.type === "subtitle" || clip.type === "filter" || clip.type === "effect") return;
    let videoInfo = videoPool.get(clip.id);
    if (!videoInfo) {
      videoInfo = createVideoEl(clip.id, clip.source);
    }
    syncVideoSingle(videoInfo, clip, time);
  });

  const activeAudioClips = activeList.filter(item => item.clip.type === 'audio')
  const activeAudioIds = new Set(activeAudioClips.map(i => i.clip.id))

  for (const [cid, audioInfo] of audioPool) {
    if (!activeAudioIds.has(cid)) {
      audioInfo.audio.pause()
    }
  }

    activeAudioClips.forEach(({ clip }) => {
    let audioInfo = audioPool.get(clip.id)
    if (!audioInfo) {
        const audioEl = document.createElement('audio')
        audioEl.crossOrigin = "anonymous"
        audioEl.style.width = '1px'
        audioEl.style.height = '1px'
        audioEl.style.opacity = '0'
        audioEl.preload = 'metadata'
        audioEl.src = clip.source
        audioEl._lastSeekMs = 0
        document.body.appendChild(audioEl)
        audioPool.set(clip.id, {
          audio: audioEl,
          audioSource: null,
          clipGainNode: null,
          useNativeVolume: false
        })
        audioInfo = audioPool.get(clip.id)
      }
      const { audio } = audioInfo
      const targetVolume = clip.volume ?? 1.0

      const timelineOffset = time - clip.startTime
      const clipRate = clip.playbackRate ?? 1.0
      let targetInnerTime = clip.trimStart + timelineOffset / clipRate;
      targetInnerTime = Math.max(clip.trimStart, Math.min(clip.trimEnd, targetInnerTime))

      const clipEnd = clip.endTime
      const inRange = time >= clip.startTime && time <= clipEnd
      if (!inRange) {
        audio.pause()
        return
      }

      if (audioCtx && !audioInfo.audioSource && !audioInfo.useNativeVolume) {
        try {
          audioInfo.audioSource = audioCtx.createMediaElementSource(audio);
          audioInfo.clipGainNode = audioCtx.createGain();
          audioInfo.clipGainNode.gain.value = targetVolume;
          audioInfo.audioSource.connect(audioInfo.clipGainNode);
          audioInfo.clipGainNode.connect(masterGain);
        } catch (err) {
          audioInfo.useNativeVolume = true;
        }
      }
      // ✅每一帧直接更新gain，拖动滑块立刻生效；不会重复创建节点
      if(audioInfo.clipGainNode){
        audioInfo.clipGainNode.gain.value = targetVolume;
      }else if(audioInfo.useNativeVolume){
        audio.volume = Math.min(targetVolume, 1.0);
      }

      const diff = Math.abs(audio.currentTime - targetInnerTime)
      const nowMs = performance.now()
      if (diff > SYNC_TOLERANCE && nowMs - audio._lastSeekMs > SEEK_COOLDOWN) {
        audio.currentTime = targetInnerTime
        audio._lastSeekMs = nowMs
      }
      audio.playbackRate = 1.0

      if (isPlaying.value) {
        if (audio.paused) audio.play().catch(() => { })
      } else {
        audio.pause()
      }
  })
}

function getTextBound(ctx, text, fontSize) {
    const lines = text.split('\n');
    const lineHeight = fontSize * 1.3;
    ctx.font = `${fontSize}px sans-serif`;
    let maxW = 0;
    for(let line of lines) {
        const m = ctx.measureText(line);
        if(m.width > maxW) maxW = m.width;
    }
    const totalH = lines.length * lineHeight;
    return { w: maxW, h: totalH };
}


function getBaseDrawSize(naturalW, naturalH) {
  const cw = props.canvasWidth;
  const ch = props.canvasHeight;
  const r1 = naturalW / naturalH;
  const r2 = cw / ch;
  let w, h;
  if (r1 > r2) {
    w = cw;
    h = cw / r1;
  } else {
    h = ch;
    w = ch * r1;
  }
  return { w, h };
}

// ---------------------- GIF 二进制解析核心函数 ----------------------
function isGifUrl(url) {
  if (!url) return false;
  const u = url.toLowerCase();
  return u.endsWith(".gif");
}

async function loadAsset(url) {
  if (assetCache.has(url)) return assetCache.get(url);
  const asset = {
    type: null,
    img: null,
    gifFrames: null,
    gifWidth: 0,
    gifHeight: 0,
    gifTotalDuration: 0,
    gifTime: 0,
    loaded: false
  };

  if (isGifUrl(url)) {
    const resp = await fetch(url, { mode: "cors" });
    const arrayBuf = await resp.arrayBuffer();
    const gif = parseGIF(new Uint8Array(arrayBuf));
    const frames = decompressFrames(gif, true);

    let totalDur = 0;
    frames.forEach(f => {
      totalDur += f.delay;
    });

    asset.type = "gif";
    asset.gifFrames = frames;
    asset.gifWidth = gif.lsd.width;
    asset.gifHeight = gif.lsd.height;
    asset.gifTotalDuration = totalDur;
    asset.loaded = true;
  } else {
    const img = new Image();
    img.crossOrigin = "anonymous";
    await new Promise((res, rej) => {
      img.onload = res;
      img.onerror = rej;
      img.src = url;
    });
    asset.type = "image";
    asset.img = img;
    asset.loaded = true;
  }

  if (assetCache.size > MAX_CACHE) {
    const firstKey = assetCache.keys().next().value;
    assetCache.delete(firstKey);
    const oldItem = gifCanvasCache.get(firstKey);
    if (oldItem?.snapshotStack) {
      oldItem.snapshotStack.forEach(bmp => bmp.close());
    }
    gifCanvasCache.delete(firstKey);
  }
  assetCache.set(url, asset);
  return asset;
}

function getGifFrameCanvas(asset, url) {
  const { gifFrames, gifWidth, gifHeight, gifTotalDuration, gifTime } = asset;
  if (!gifFrames?.length || gifWidth <= 0 || gifHeight <= 0) return null;

  let cacheItem = gifCanvasCache.get(url);
  if (!cacheItem) {
    const offCanvas = document.createElement("canvas");
    offCanvas.width = gifWidth;
    offCanvas.height = gifHeight;
    const offCtx = offCanvas.getContext("2d");
    cacheItem = {
      offCanvas,
      offCtx,
      snapshotStack: []
    };
    gifCanvasCache.set(url, cacheItem);
  }
  const { offCanvas, offCtx, snapshotStack } = cacheItem;

  const loopTime = asset.gifTime % gifTotalDuration;

  if (loopTime < 1) {
    offCtx.clearRect(0, 0, gifWidth, gifHeight);
    snapshotStack.forEach(bmp => bmp.close());
    snapshotStack.length = 0;
  }

  let accum = 0;
  let targetFrameIndex = 0;
  for (let i = 0; i < gifFrames.length; i++) {
    const frame = gifFrames[i];
    if (accum + frame.delay >= loopTime) {
      targetFrameIndex = i;
      break;
    }
    accum += frame.delay;
  }

  for (let i = 0; i <= targetFrameIndex; i++) {
    const frame = gifFrames[i];
    const prevFrame = i > 0 ? gifFrames[i - 1] : null;
    const fw = frame.dims.width;
    const fh = frame.dims.height;
    const fx = Math.round(frame.dims.left ?? 0);
    const fy = Math.round(frame.dims.top ?? 0);

    if (prevFrame) {
      switch (prevFrame.disposal) {
        case 0:
        case 1: break;
        case 2: {
          const pW = prevFrame.dims.width;
          const pH = prevFrame.dims.height;
          const pX = Math.round(prevFrame.dims.left);
          const pY = Math.round(prevFrame.dims.top);
          offCtx.clearRect(pX, pY, pW, pH);
          break;
        }
        case 3: {
          if (snapshotStack.length > 0) {
            const prevSnap = snapshotStack.pop();
            offCtx.clearRect(0, 0, gifWidth, gifHeight);
            offCtx.drawImage(prevSnap, 0, 0);
            prevSnap.close();
          }
          break;
        }
      }
    }

    if (frame.disposal === 3) {
      const snap = offCanvas.transferToImageBitmap();
      snapshotStack.push(snap);
      while (snapshotStack.length > MAX_SNAPSHOT_COUNT) {
        const old = snapshotStack.shift();
        old.close();
      }
    }

    if (!frame.patch || frame.patch.length === 0) {
      offCtx.clearRect(fx, fy, fw, fh);
      continue;
    }

    try {
      const imageData = new ImageData(
        new Uint8ClampedArray(frame.patch),
        fw,
        fh
      );
      offCtx.putImageData(imageData, fx, fy);
    } catch (err) {
      console.warn("GIF帧putImageData异常", fx, fy, err);
    }
  }

  return offCanvas;
}

/**
 * 计算旋转后矩形的四个角点
 */
function getRotatedRectCorners(cx, cy, w, h, deg) {
  const rad = (deg || 0) * Math.PI / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);

  const halfW = w / 2;
  const halfH = h / 2;

  // 未旋转的四个角
  const corners = [
    { x: -halfW, y: -halfH },
    { x:  halfW, y: -halfH },
    { x:  halfW, y:  halfH },
    { x: -halfW, y:  halfH }
  ];

  // 绕中心点旋转后再平移到 cx / cy
  return corners.map(p => ({
    x: cx + p.x * cos - p.y * sin,
    y: cy + p.x * sin + p.y * cos
  }));
}

// 包围盒、脏矩形
function getClipBoundingBox(clip) {
  const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1, rotate:0 };
  let baseW, baseH;
  if (clip.type === 'subtitle') {
    const style = clip.style || { fontSize: 36 };
    const bound = getTextBound(ctx2d, clip.text, style.fontSize);
    baseW = bound.w;
    baseH = bound.h;
  } else if (clip.type === 'filter' || clip.type === 'effect') {
    return { x:0, y:0, w:props.canvasWidth, h:props.canvasHeight };
  } else {
    const natW = clip.naturalWidth || 60;
    const natH = clip.naturalHeight || 60;
    const base = getBaseDrawSize(natW, natH);
    baseW = base.w;
    baseH = base.h;
  }
  const halfW = baseW / 2 * tf.scale;
  const halfH = baseH / 2 * tf.scale;
  return {
    x: tf.x - halfW,
    y: tf.y - halfH,
    w: halfW * 2,
    h: halfH * 2
  };
}
function addDirtyRect(rect) {
  const { x, y, w, h } = rect;
  if (w <= 0 || h <= 0) return;
  dirtyRects.push({ x, y, w, h });
}
function mergeDirtyRects() {
  if (dirtyRects.length === 0) return [];
  const result = [];
  for (const r of dirtyRects) {
    let merged = false;
    for (let i = 0; i < result.length; i++) {
      const mr = result[i];
      if (
        r.x < mr.x + mr.w && r.x + r.w > mr.x &&
        r.y < mr.y + mr.h && r.y + r.h > mr.y
      ) {
        const nx = Math.min(mr.x, r.x);
        const ny = Math.min(mr.y, r.y);
        const nw = Math.max(mr.x + mr.w, r.x + r.w) - nx;
        const nh = Math.max(mr.y + mr.h, r.y + r.h) - ny;
        result[i] = { x: nx, y: ny, w: nw, h: nh };
        merged = true;
        break;
      }
    }
    if (!merged) result.push({ ...r });
  }
  dirtyRects = [];
  return result;
}

// 渲染循环
function renderLoop(timestamp) {
  if (!isPlaying.value) return;
  const delta = ((timestamp - (window._lastTs || timestamp)) / 1000) * PLAY_SPEED;
  window._lastTs = timestamp;
  displayTime.value += Math.min(delta, MAX_DELTA_SEC);

  for (const [_, asset] of assetCache) {
    if (asset.type === "gif" && asset.loaded) {
      asset.gifTime += delta * 1000;
      asset.gifTime = asset.gifTime % asset.gifTotalDuration;
    }
  }

  if (displayTime.value >= totalDuration.value) {
    pause();
    displayTime.value = totalDuration.value;
    emit("seeked", displayTime.value);
    forceFullRender = true;
    drawFrame();
    return;
  }

  syncAllActiveVideos(displayTime.value);
  emit("timeupdate", displayTime.value);
  drawFrame().then(() => {
    animationId = requestAnimationFrame(renderLoop);
  });
}

function drawClipSelectBox(clip, baseSize) {
  const tf = clip.transform;
  ctx2d.save();
  ctx2d.translate(tf.x, tf.y);
  ctx2d.scale(tf.scale, tf.scale);
  ctx2d.strokeStyle = "#4096ff";
  ctx2d.lineWidth = 2;
  ctx2d.strokeRect(-baseSize.w / 2, -baseSize.h / 2, baseSize.w, baseSize.h);
  ctx2d.restore();

  ctx2d.fillStyle = "#4096ff";
  const handleSize = 8;
  const halfW = baseSize.w * tf.scale;
  const halfH = baseSize.h * tf.scale;
  HANDLES.forEach(h => {
    const hx = tf.x + h.dx * halfW;
    const hy = tf.y + h.dy * halfH;
    ctx2d.fillRect(hx - handleSize / 2, hy - handleSize / 2, handleSize, handleSize);
  });
}

// 主绘制：先2D绘制到离屏画布，再交给WebGL做滤镜+特效后处理
async function drawFrame() {
  if (!ctx2d || !cacheCanvas || !cacheCtx || !offscreen2dCanvas) return;

  // =========新增：forceFullRender时，等待范围内视频元数据简单就绪，避免黑屏绘制空帧 =========
  if(forceFullRender){
    const activeList = getActiveClips(displayTime.value);
    for(const {clip} of activeList){
      if(clip.type !== "video") continue;
      const info = videoPool.get(clip.id);
      if(!info) continue;
      const video = info.video;
      if(video.readyState <1){
        await new Promise(resolve=>{
          const onLoaded = ()=>{
            video.removeEventListener('loadedmetadata', onLoaded);
            resolve(null);
          }
          video.addEventListener('loadedmetadata', onLoaded);
        })
      }
    }
  }

  const activeList = getActiveClips(displayTime.value);
  const videoClips = activeList.filter(i => i.clip.type === 'video');
  const stickerClips = activeList.filter(i => i.clip.type === 'sticker');
  const subClips = activeList.filter(i => i.clip.type === 'subtitle');
  const filterClips = activeList.filter(i => i.clip.type === 'filter').map(i=>i.clip);

  // 提取生效特效，计算片段内进度progress
  const activeEffectClips = [];
  activeList.forEach(({clip})=>{
    if(clip.type !== 'effect') return
    const duration = clip.endTime - clip.startTime
    let progress = duration <= 0 ? 1 : (displayTime.value - clip.startTime) / duration
    progress = Math.max(0, Math.min(1, progress))
    activeEffectClips.push({
      ...clip,
      progress
    })
  })

  // =========【新增：检测转场片段】==========
  const transitionClipItem = activeList.find(({clip}) => clip.type === 'transition');
  inTransitionRender = false;
  activeTransitionInfo = null;
  if(transitionClipItem){
    const transClip = transitionClipItem.clip;
    const tStart = transClip.startTime;
    const tEnd = transClip.endTime;

    const dur = tEnd - tStart;
    let progress = dur <=0 ? 1 : (displayTime.value - tStart) / dur;


    progress = Math.max(0, Math.min(1, progress));

    // 修复：收集全部视频clip，筛选与转场时间有交集的，排序取倒数第1、2个
    const allVideoClips = props.trackData.tracks
      .flatMap(t=>t.clips)
      .filter(c=>c.type === 'video')
      .filter(c => !(c.endTime <= tStart || c.startTime > tEnd));

    if(allVideoClips.length >=2){
      // 按startTime升序
      allVideoClips.sort((a,b)=>a.startTime - b.startTime);
      const clipA = allVideoClips[allVideoClips.length-2];
      const clipB = allVideoClips[allVideoClips.length-1];

      inTransitionRender = true;
      activeTransitionInfo = {
        progress,
        type: TRANS_SHADER_MAP[transClip.transitionType] ?? 0,
        clipA,
        clipB
      }
      // 分别渲染A画面到transCanvasA，B画面到transCanvasB
      transCtxA.clearRect(0,0,props.canvasWidth,props.canvasHeight);
      await renderSingleVideoToCanvas(transCtxA, clipA, displayTime.value);

      transCtxB.clearRect(0,0,props.canvasWidth,props.canvasHeight);
      await renderSingleVideoToCanvas(transCtxB, clipB, displayTime.value);
    }
  }


  dirtyRects = [];
  videoClips.forEach(({ clip }) => addDirtyRect(getClipBoundingBox(clip)));
  for (const { clip } of stickerClips) addDirtyRect(getClipBoundingBox(clip));
  if (dragState.value.active && dragState.value.clip) addDirtyRect(getClipBoundingBox(dragState.value.clip));
  if (selectedClipId.value) {
    const sel = activeList.find(i => i.clip.id === selectedClipId.value);
    if (sel) addDirtyRect(getClipBoundingBox(sel.clip));
  }
  if(filterClips.length>0) addDirtyRect({x:0,y:0,w:props.canvasWidth,h:props.canvasHeight});
  // 特效全屏，强制整帧重绘
  if(activeEffectClips.length>0) addDirtyRect({x:0,y:0,w:props.canvasWidth,h:props.canvasHeight});

  const mergedRects = mergeDirtyRects();

  if (forceFullRender || mergedRects.length === 0) {
    ctx2d.fillStyle = "#000000";
    ctx2d.fillRect(0, 0, props.canvasWidth, props.canvasHeight);
    await renderAllLayers(ctx2d, videoClips, stickerClips, subClips);

    cacheCtx.clearRect(0,0,cacheCanvas.width,cacheCanvas.height);
    cacheCtx.drawImage(offscreen2dCanvas, 0, 0);
    forceFullRender = false;
  } else {
    ctx2d.drawImage(cacheCanvas, 0,0);
    for(const rect of mergedRects){
      const {x,y,w,h} = rect;
      ctx2d.save();
      ctx2d.beginPath();
      ctx2d.rect(x,y,w,h);
      ctx2d.clip();
      ctx2d.fillStyle="#000";
      ctx2d.fillRect(x,y,w,h);
      await renderLayersInRect(ctx2d, videoClips, stickerClips, subClips, rect);
      ctx2d.restore();
    }
    cacheCtx.drawImage(offscreen2dCanvas,0,0);
  }

  // ===== WebGL后处理滤镜 + 特效渲染输出到屏幕画布 =====
  const passBCanvas = inTransitionRender ? transCanvasB : null;
  webglRender(offscreen2dCanvas, filterClips, activeEffectClips, passBCanvas);
  lastRenderTime = performance.now();
}

async function renderSingleVideoToCanvas(drawCtx, videoClip, time) {
  const tf = videoClip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1 };
  const natW = videoClip.naturalWidth || 1280;
  const natH = videoClip.naturalHeight || 720;
  const baseSize = getBaseDrawSize(natW, natH);
  const videoInfo = videoPool.get(videoClip.id);
  const drawSource = videoInfo?.video;
  if (!drawSource) return;
  drawCtx.save();
  drawCtx.translate(tf.x, tf.y);
  drawCtx.scale(tf.scale, tf.scale);
  drawCtx.globalAlpha = videoClip.opacity ?? 1.0;
  drawCtx.drawImage(drawSource, -baseSize.w / 2, -baseSize.h / 2, baseSize.w, baseSize.h);
  drawCtx.restore();
}

async function renderAllLayers(drawCtx, videoClips, stickerClips, subClips) {
  videoClips.forEach(({ clip }) => {
    const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1 };
    const natW = clip.naturalWidth || 1280;
    const natH = clip.naturalHeight || 720;
    const baseSize = getBaseDrawSize(natW, natH);
    const videoInfo = videoPool.get(clip.id);
    const drawSource = videoInfo?.video;
    if (!drawSource) return;
    drawCtx.save();
    drawCtx.translate(tf.x, tf.y);
    drawCtx.scale(tf.scale, tf.scale);
    drawCtx.globalAlpha = clip.opacity ?? 1.0;
    drawCtx.drawImage(drawSource, -baseSize.w / 2, -baseSize.h / 2, baseSize.w, baseSize.h);
    drawCtx.restore();
    if (selectedClipId.value === clip.id) drawClipSelectBox(clip, baseSize);
  });

  for (const { clip } of stickerClips) {
    const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1 };
    const stickerRotate = clip.rotate ?? 0;
    const natW = clip.naturalWidth || 60;
    const natH = clip.naturalHeight || 60;
    const baseSize = getBaseDrawSize(natW, natH);
    let asset;
    try { asset = await loadAsset(clip.source); } catch (e) { continue; }
    if (!asset.loaded) continue;
    let drawSource;
    if (asset.type === "gif") drawSource = getGifFrameCanvas(asset, clip.source);
    else drawSource = asset.img;
    if (!drawSource) continue;

    drawCtx.save();
    drawCtx.translate(tf.x, tf.y);
    drawCtx.scale(tf.scale, tf.scale);
    drawCtx.rotate(stickerRotate * Math.PI / 180);
    drawCtx.globalAlpha = clip.opacity ?? 1;
    drawCtx.drawImage(drawSource, -baseSize.w / 2, -baseSize.h / 2, baseSize.w, baseSize.h);
    drawCtx.globalAlpha = 1;
    drawCtx.restore();
    if (selectedClipId.value === clip.id) drawClipSelectBox(clip, baseSize);
  }

  subClips.forEach(({ clip }) => {
    const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1, rotate:0 };
    const style = clip.style || { fontSize: 36, fill: '#ffffff', stroke:'#000000', strokeWidth:3 };
    const baseBound = getTextBound(ctx2d, clip.text, style.fontSize);
    drawCtx.save();
    drawCtx.translate(tf.x, tf.y);
    drawCtx.scale(tf.scale, tf.scale);
    drawCtx.rotate(tf.rotate * Math.PI / 180);

    // 使用多行绘制，坐标原点现在是 (0,0) transform坐标系内
    drawMultilineText(
        drawCtx,
        clip.text,
        0,
        0,
        style.fontSize,
        style.fill,
        style.stroke,
        style.strokeWidth
    );

    drawCtx.restore();

    if (selectedClipId.value === clip.id) {
      const rotate = tf.rotate ?? 0;

      drawCtx.save();
      drawCtx.translate(tf.x, tf.y);
      drawCtx.scale(tf.scale, tf.scale);
      drawCtx.rotate(rotate * Math.PI / 180);
      drawCtx.strokeStyle = "#4096ff";
      drawCtx.lineWidth = 2;
      drawCtx.strokeRect(-baseBound.w / 2, -baseBound.h / 2, baseBound.w, baseBound.h);
      drawCtx.restore();

      drawCtx.fillStyle = "#4096ff";
      const handleSize = 8;

      const corners = getRotatedRectCorners(
        tf.x,
        tf.y,
        baseBound.w * tf.scale,
        baseBound.h * tf.scale,
        rotate
      );

      corners.forEach(point => {
        drawCtx.fillRect(
          point.x - handleSize / 2,
          point.y - handleSize / 2,
          handleSize,
          handleSize
        );
      });
    }
  });
}

/**
 * 绘制支持 \n 换行的文本
 * @param {CanvasRenderingContext2D} ctx
 * @param {string} text 带\n换行的文本
 * @param {number} x 绘制中心点
 * @param {number} y 绘制中心点
 * @param {number} fontSize
 * @param {string} fill
 * @param {string} stroke
 * @param {number} strokeWidth
 * @param {number} lineHeightMultiple 行高倍数
 */
function drawMultilineText(ctx, text, x, y, fontSize, fill, stroke, strokeWidth, lineHeightMultiple = 1.3) {
    const lines = text.split('\n');
    const lineHeight = fontSize * lineHeightMultiple;
    // 整体文本块垂直居中，计算起始y偏移
    const totalHeight = (lines.length - 1) * lineHeight;
    let startY = y - totalHeight / 2;

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `${fontSize}px sans-serif`;

    for (let i = 0; i < lines.length; i++) {
        const lineY = startY + i * lineHeight;
        // 描边
        if (stroke && Number(strokeWidth) > 0) {
            ctx.strokeStyle = stroke;
            ctx.lineWidth = strokeWidth;
            ctx.strokeText(lines[i], x, lineY);
        }
        // 填充文字
        ctx.fillStyle = fill;
        ctx.fillText(lines[i], x, lineY);
    }
}

async function renderLayersInRect(drawCtx, videoClips, stickerClips, subClips, rect) {
  const {x,y,w,h} = rect;
  const intersect = (box) => {
    return box.x < x+w && box.x+box.w > x && box.y < y+h && box.y+box.h > y;
  };
  for(const {clip} of videoClips){
    const box = getClipBoundingBox(clip);
    if(!intersect(box)) continue;
    const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1 };
    const natW = clip.naturalWidth || 1280;
    const natH = clip.naturalHeight || 720;
    const baseSize = getBaseDrawSize(natW, natH);
    const videoInfo = videoPool.get(clip.id);
    const drawSource = videoInfo?.video;
    if (!drawSource) continue;
    drawCtx.save();
    drawCtx.translate(tf.x, tf.y);
    drawCtx.scale(tf.scale, tf.scale);
    drawCtx.globalAlpha = clip.opacity ?? 1.0;
    drawCtx.drawImage(drawSource, -baseSize.w / 2, -baseSize.h / 2, baseSize.w, baseSize.h);
    drawCtx.restore();
    if (selectedClipId.value === clip.id) drawClipSelectBox(clip, baseSize);
  }
  for (const { clip } of stickerClips) {
      const box = getClipBoundingBox(clip);
      if(!intersect(box)) continue;
      const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1 };
      const stickerRotate = clip.rotate ?? 0;
      const natW = clip.naturalWidth || 60;
      const natH = clip.naturalHeight || 60;
      const baseSize = getBaseDrawSize(natW, natH);
      let asset;
      try { asset = await loadAsset(clip.source); } catch (e) { continue; }
      if (!asset.loaded) continue;
      let drawSource;
      if (asset.type === "gif") drawSource = getGifFrameCanvas(asset, clip.source);
      else drawSource = asset.img;
      if (!drawSource) continue;
      drawCtx.save();
      drawCtx.translate(tf.x, tf.y);
      drawCtx.scale(tf.scale, tf.scale);
      drawCtx.rotate(stickerRotate * Math.PI / 180);
      drawCtx.globalAlpha = clip.opacity ??1;
      drawCtx.drawImage(drawSource, -baseSize.w / 2, -baseSize.h / 2, baseSize.w, baseSize.h);
      drawCtx.globalAlpha =1;
      drawCtx.restore();
      if (selectedClipId.value === clip.id) drawClipSelectBox(clip, baseSize);
    }
    for(const {clip} of subClips){
    const box = getClipBoundingBox(clip);
    if(!intersect(box)) continue;
    const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale:1, rotate:0 };
    const style = clip.style || { fontSize: 36, fill: '#ffffff', stroke:'#000000', strokeWidth:3 };
    const baseBound = getTextBound(drawCtx, clip.text, style.fontSize);
    drawCtx.save();
    drawCtx.translate(tf.x, tf.y);
    drawCtx.scale(tf.scale, tf.scale);
    drawCtx.rotate(tf.rotate * Math.PI / 180);

    drawMultilineText(
        drawCtx,
        clip.text,
        0,
        0,
        style.fontSize,
        style.fill,
        style.stroke,
        style.strokeWidth
    );

    drawCtx.restore();

    if (selectedClipId.value === clip.id) {
      const rotate = tf.rotate ?? 0;

      drawCtx.save();
      drawCtx.translate(tf.x, tf.y);
      drawCtx.scale(tf.scale, tf.scale);
      drawCtx.rotate(rotate * Math.PI / 180);
      drawCtx.strokeStyle = "#4096ff";
      drawCtx.lineWidth = 2;
      drawCtx.strokeRect(-baseBound.w / 2, -baseBound.h / 2, baseBound.w, baseBound.h);
      drawCtx.restore();

      drawCtx.fillStyle = "#4096ff";
      const handleSize = 8;

      const corners = getRotatedRectCorners(
        tf.x,
        tf.y,
        baseBound.w * tf.scale,
        baseBound.h * tf.scale,
        rotate
      );

      corners.forEach(point => {
        drawCtx.fillRect(
          point.x - handleSize / 2,
          point.y - handleSize / 2,
          handleSize,
          handleSize
        );
      });
    }
  }

}

// 播放
async function play() {
  initAudioContext();
  if (audioCtx.state === "suspended") await audioCtx.resume();
  if (isPlaying.value) return;
  isPlaying.value = true;
  emit("play");
  window._lastTs = performance.now();
  syncAllActiveVideos(displayTime.value);
  animationId = requestAnimationFrame(renderLoop);
}

function pause() {
  isPlaying.value = false;
  emit("pause");
  if (animationId) cancelAnimationFrame(animationId);
  for (const { video } of videoPool.values()) {
    video.pause();
  }
  for (const { audio } of audioPool.values()) {
    audio.pause();
  }
}

async function setCurrentTime(sec, isUserSeek = false) {
  displayTime.value = Math.max(0, Math.min(sec, totalDuration.value));
  if (isUserSeek) {
    pause();
    forceFullRender = true; // 用户拖动/新增素材，强制整帧重绘
  } else if (isPlaying.value) {
    window._lastTs = performance.now();
  }
  syncAllActiveVideos(displayTime.value);
  await drawFrame();
  emit("seeked", displayTime.value);
}

const isMute = ref(false);
function toggleMute() {
  isMute.value = !isMute.value;
  const gainVal = isMute.value ? 0 : 1;
  if (masterGain) {
    masterGain.gain.value = gainVal;
  }
  for (const [_, info] of videoPool) {
    if (info.useNativeVolume) {
      info.video.volume = gainVal;
    }
  }
  for (const [_, info] of audioPool) {
    if (info.useNativeVolume) {
      info.audio.volume = gainVal;
    }
  }
}

// 鼠标交互（坐标转换到画布）
function hitHandle(clip, mx, my) {
  const tf = clip.transform;
  let baseW, baseH;
  if (clip.type === 'subtitle') {
    const style = clip.style || { fontSize: 36 };
    const bound = getTextBound(ctx2d, clip.text, style.fontSize);
    baseW = bound.w;
    baseH = bound.h;
  } else if(clip.type === 'filter' || clip.type === 'effect'){
    return null;
  } else {
    const natW = clip.naturalWidth || 1280;
    const natH = clip.naturalHeight || 720;
    const base = getBaseDrawSize(natW, natH);
    baseW = base.w;
    baseH = base.h;
  }
  const halfW = baseW * tf.scale;
  const halfH = baseH * tf.scale;
  const range = 12;
  for (const h of HANDLES) {
    const hx = tf.x + h.dx * halfW;
    const hy = tf.y + h.dy * halfH;
    const dist = Math.hypot(mx - hx, my - hy);
    if (dist < range) {
      return h.key;
    }
  }
  return null;
}

function isPointInClip(clip, mx, my) {
  if(clip.type === 'filter' || clip.type === 'effect') return false;
  const tf = clip.transform || { x: props.canvasWidth / 2, y: props.canvasHeight / 2, scale: 1 };
  let baseW, baseH;
  if (clip.type === 'subtitle') {
    const style = clip.style || { fontSize: 36 };
    const bound = getTextBound(ctx2d, clip.text, style.fontSize);
    baseW = bound.w;
    baseH = bound.h;
  } else {
    const natW = clip.naturalWidth || 1280;
    const natH = clip.naturalHeight || 720;
    const base = getBaseDrawSize(natW, natH);
    baseW = base.w;
    baseH = base.h;
  }
  const hw = baseW / 2 * tf.scale;
  const hh = baseH / 2 * tf.scale;
  return mx >= tf.x - hw && mx <= tf.x + hw && my >= tf.y - hh && my <= tf.y + hh;
}

function handleCanvasMouseDown(e) {
  const rect = glCanvasRef.value.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const activeList = [...getActiveClips(displayTime.value)].reverse();

  let hitClip = null;
  let hitKey = null;
  for (const { clip } of activeList) {
    if (clip.type === "audio" || clip.type === 'filter' || clip.type === 'effect') continue;
    const k = hitHandle(clip, mx, my);
    if (k) {
      hitClip = clip;
      hitKey = k;
      break;
    }
  }
  if (!hitClip) {
    for (const { clip } of activeList) {
      if (clip.type === "audio" || clip.type === 'filter' || clip.type === 'effect') continue;
      if (isPointInClip(clip, mx, my)) {
        hitClip = clip;
        break;
      }
    }
  }

  if (hitClip) {
    dragState.value.active = true;
    dragState.value.clip = hitClip;
    dragState.value.startX = mx;
    dragState.value.startY = my;
    dragState.value.originX = hitClip.transform.x;
    dragState.value.originY = hitClip.transform.y;
    dragState.value.originScale = hitClip.transform.scale;
    dragState.value.handleKey = hitKey;
    dragState.value.mode = hitKey ? "scale" : "move";
    selectedClipId.value = hitClip.id;
    emit("clip-select", hitClip);
  } else {
    selectedClipId.value = null;
    emit("clip-select", null);
  }
  drawFrame();
}

function handleCanvasMouseMove(e) {
  if (!dragState.value.active || !dragState.value.clip) return;
  const rect = glCanvasRef.value.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const ds = dragState.value;
  const clip = ds.clip;

  if (ds.mode === "move") {
    const dx = mx - ds.startX;
    const dy = my - ds.startY;
    clip.transform.x = ds.originX + dx;
    clip.transform.y = ds.originY + dy;
  } else if (ds.mode === "scale") {
    const dx = mx - clip.transform.x;
    const dy = my - clip.transform.y;
    let baseW, baseH;
    if (clip.type === 'subtitle') {
      const style = clip.style || { fontSize: 36 };
      const bound = getTextBound(ctx2d, clip.text, style.fontSize);
      baseW = bound.w;
      baseH = bound.h;
    } else {
      const natW = clip.naturalWidth || 1280;
      const natH = clip.naturalHeight || 720;
      const base = getBaseDrawSize(natW, natH);
      baseW = base.w;
      baseH = base.h;
    }
    let factor;
    switch (ds.handleKey) {
      case "rb": factor = Math.max(dx / (baseW / 2), dy / (baseH / 2)); break;
      case "lt": factor = Math.max(-dx / (baseW / 2), -dy / (baseH / 2)); break;
      case "rt": factor = Math.max(dx / (baseW / 2), -dy / (baseH / 2)); break;
      case "lb": factor = Math.max(-dx / (baseW / 2), dy / (baseH / 2)); break;
      default: factor = 1;
    }
    clip.transform.scale = Math.max(factor, 0.15);
  }
  drawFrame();
}

function handleCanvasMouseUp() {
  if (!dragState.value.active) return;
  emit("clip-update", dragState.value.clip);
  dragState.value.active = false;
  dragState.value.clip = null;
}

// 初始化
nextTick(() => {
  const canvas = glCanvasRef.value;
  canvas.width = props.canvasWidth;
  canvas.height = props.canvasHeight;

  offscreen2dCanvas = document.createElement("canvas");
  offscreen2dCanvas.width = props.canvasWidth;
  offscreen2dCanvas.height = props.canvasHeight;
  ctx2d = offscreen2dCanvas.getContext("2d");

  cacheCanvas = document.createElement("canvas");
  cacheCanvas.width = props.canvasWidth;
  cacheCanvas.height = props.canvasHeight;
  cacheCtx = cacheCanvas.getContext("2d");

  transCanvasA = document.createElement("canvas");
  transCanvasA.width = props.canvasWidth;
  transCanvasA.height = props.canvasHeight;
  transCtxA = transCanvasA.getContext("2d");

  transCanvasB = document.createElement("canvas");
  transCanvasB.width = props.canvasWidth;
  transCanvasB.height = props.canvasHeight;
  transCtxB = transCanvasB.getContext("2d");

  initWebGL();
  forceFullRender = true;
  drawFrame();
});


watch(() => props.currentTime, async (t) => {
  displayTime.value = t;
  forceFullRender = true;
  await drawFrame();
}, { flush: "post" });

watch(() => props.trackData, async () => {
  forceFullRender = true;
  await drawFrame();
}, { deep: true, flush: "post" });

onUnmounted(() => {
  pause();
  if (animationId) cancelAnimationFrame(animationId);

  for (const [_, cacheItem] of gifCanvasCache) {
    if (cacheItem.snapshotStack) {
      cacheItem.snapshotStack.forEach(bmp => bmp.close());
    }
  }
  gifCanvasCache.clear();

  for (const [cid, { video, audioSource, clipGainNode }] of videoPool) {
    if(audioSource) audioSource.disconnect();
    if(clipGainNode) clipGainNode.disconnect();
    video.pause();
    video.src = "";
    video.remove();
  }
  videoPool.clear();

  assetCache.clear();

  if (audioCtx) audioCtx.close();

  for (const [cid, { audio, audioSource, clipGainNode }] of audioPool) {
    if(audioSource) audioSource.disconnect();
    if(clipGainNode) clipGainNode.disconnect();
    audio.pause()
    audio.src = ''
    audio.remove()
  }
  audioPool.clear()

  // 释放WebGL资源
  if(gl){
    gl.deleteTexture(glTextureInput);
    gl.deleteTexture(glTextureB);
    if(glNoiseTexture) gl.deleteTexture(glNoiseTexture); // 释放噪声纹理
    gl.deleteBuffer(glVbo);
    gl.deleteProgram(glProgram);
  }

  gl = null;
  cacheCanvas = null;
  cacheCtx = null;
  offscreen2dCanvas = null;
  ctx2d = null;
});

defineExpose({
  play,
  pause,
  toggleMute,
  setCurrentTime
});
</script>

<style scoped>
.preview-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.preview-canvas {
  border: 1px solid #3a3a4c;
  background: #000;
}
.control-bar {
  display: flex;
  gap: 8px;
}
button {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  background: #333644;
  color: #fff;
  cursor: pointer;
}
</style>
