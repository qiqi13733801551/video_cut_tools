<template>
  <div class="editor-wrap">
    <!-- 顶部导航栏 -->
    <div class="editor-header">
      <div class="header-left">
        <span>在线剪辑工具</span>
      </div>
      <div class="header-right">
        <button class="btn" @click="saveTrackDate()">保存</button>
        <button class="btn primary" @click="openExportDialog()">导出</button>
      </div>
    </div>
    <div class="editor-body">
      <!-- 左侧资源库 -->
      <div class="resource-sidebar">
        <div class="tab-group">
          <span
            v-for="tab in resourceTabs"
            :key="tab.type"
            :class="['tab-item', { active: activeTab === tab.type }]"
            @click="activeTab = tab.type"
          >
            {{ tab.label }}
          </span>
        </div>
        <div class="resource-content">
          <!-- 视频面板 -->
          <div v-if="activeTab === 'video'">
            <div class="import-btn" @click="videoFileInput.click()">+ 导入视频素材</div>
            <input
              ref="videoFileInput"
              type="file"
              accept="video/*"
              multiple
              style="display:none"
              @change="handleSelectVideo"
            />
            <div class="material-list">
              <div
                v-for="item in getMaterialList()"
                :key="item.id"
                class="material-item"
                draggable="true"
                @dragstart="handleMaterialDragStart($event, item)"
              >
                <div
                  class="thumb"
                  :style="{ backgroundImage: item.cover ? `url(${item.cover})` : '' }"
                >
                  <div class="thumb-action">
                    <span class="btn-add" @click.stop="addMaterialToTrack(item)">+</span>
                    <span class="btn-del" @click.stop="deleteMaterial(item.id)">🗑</span>
                  </div>
                </div>
                <div class="name">{{ item.name }}</div>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'audio'">
            <div class="import-btn" @click="audioFileInput.click()">+ 导入音频素材</div>
            <input
              ref="audioFileInput"
              type="file"
              accept="audio/*"
              multiple
              style="display:none"
              @change="handleSelectAudio"
            />
            <div class="material-list">
              <div
                v-for="item in getMaterialList()"
                :key="item.id"
                class="material-item" style="width:100%;"
                draggable="true"
                @dragstart="handleMaterialDragStart($event, item)"
              >
                <div class="thumb audio-thumb" style="width:100%;height:40px;text-align:center;font-size:24px;">
                  🎵
                  <div class="thumb-action">
                    <span class="btn-add" @click.stop="addMaterialToTrack(item)">+</span>
                    <span class="btn-del" @click.stop="deleteMaterial(item.id)">🗑</span>
                  </div>
                </div>
                <div class="name">{{ item.name }}</div>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'text'">
            <div class="material-list">
              <div class="material-item" style="width:100%;">
                <div
                  class="thumb" style="width:100%;height:40px;text-align:center;"
                >
                  <div class="thumb-action">
                    <span class="btn-add" @click.stop="addSubtitleToTrack()">+</span>
                  </div>
                  <div class="name" style="font-size:24px;">示例字幕</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 贴纸Tab -->
          <div v-if="activeTab === 'sticker'">
            <div class="sticker-category-tabs">
              <span
                v-for="cat in stickerCategoryList"
                :key="cat.key"
                :class="['cat-tab', {active: activeStickerCat === cat.key}]"
                @click="activeStickerCat = cat.key"
              >
                {{ cat.label }}
              </span>
            </div>
            <div class="sticker-grid">
              <div
                v-for="sticker in currentStickerList"
                :key="sticker.src"
                class="sticker-item"
                draggable="true"
                @dragstart="handleStickerDragStart($event, sticker)"
              >
                <div class="sticker-thumb" :style="{backgroundImage: `url(${sticker.src})`}">
                  <div class="thumb-action">
                    <span class="btn-add" @click.stop="addStickerToTrack(sticker)">+</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ========== 滤镜Tab【新增】 ========== -->
          <div v-if="activeTab === 'filter'">
            <!-- 滤镜一级分类：胶片、清新、旅行、艺术 -->
            <div class="sticker-category-tabs">
              <span
                v-for="cat in filterCategoryList"
                :key="cat.key"
                :class="['cat-tab', {active: activeFilterCat === cat.key}]"
                @click="activeFilterCat = cat.key"
              >
                {{ cat.label }}
              </span>
            </div>
            <!-- 子滤镜网格列表 -->
            <div class="sticker-grid">
              <div
                v-for="filterItem in currentFilterList"
                :key="filterItem.key"
                class="sticker-item filter-item"
              >
                <div class="sticker-thumb filter-thumb">
                  <div class="filter-name-text">{{ filterItem.label }}</div>
                  <div class="thumb-action">
                    <span class="btn-add" @click.stop="addFilterToTrack(filterItem)">+</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ========== 特效Tab【新增】 ========== -->
          <div v-if="activeTab === 'effects'">
            <!-- 特效一级分类：基础 -->
            <div class="sticker-category-tabs">
              <span
                v-for="cat in effectCategoryList"
                :key="cat.key"
                :class="['cat-tab', {active: activeEffectCat === cat.key}]"
                @click="activeEffectCat = cat.key"
              >
                {{ cat.label }}
              </span>
            </div>
            <!-- 子特效网格列表 -->
            <div class="sticker-grid">
              <div
                v-for="effectItem in currentEffectList"
                :key="effectItem.key"
                class="sticker-item filter-item"
              >
                <div class="sticker-thumb filter-thumb">
                  <div class="filter-name-text">{{ effectItem.label }}</div>
                  <div class="thumb-action">
                    <span class="btn-add" @click.stop="addEffectToTrack(effectItem)">+</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- ========== 转场Tab【新增】 ========== -->
          <div v-if="activeTab === 'transition'">
            <div class="sticker-category-tabs">
              <span
                v-for="cat in transitionCategoryList"
                :key="cat.key"
                :class="['cat-tab', {active: activeTransitionCat === cat.key}]"
                @click="activeTransitionCat = cat.key"
              >
                {{ cat.label }}
              </span>
            </div>
            <div class="sticker-grid">
              <div
                v-for="transItem in currentTransitionList"
                :key="transItem.key"
                class="sticker-item filter-item"
              >
                <div class="sticker-thumb filter-thumb">
                  <div class="filter-name-text">{{ transItem.label }}</div>
                  <div class="thumb-action">
                    <span class="btn-add" @click.stop="addTransitionToTrack(transItem)">+</span>
                  </div>
                </div>
              </div>
            </div>
          </div>


        </div>
      </div>

      <div class="preview-container">
        <div class="preview-main">
          <VideoPreview
            ref="previewRef"
            :track-data="trackData"
            @timeupdate="onPreviewTimeUpdate"
            @seeked="onPreviewSeeked"
            :current-time="currentTime"
            :canvas-width="783"
            :canvas-height="450"
            @play="onPreviewPlay"
            @pause="onPreviewPause"
            @clip-select="onClipSelect"
            @clip-update="handleClipPropUpdate"
          />
        </div>
        <div class="preview-property-wrap">
          <PropertyPanel
            :selected-clip="selectedClip"
            @update:clip="handleClipPropUpdate"
          />
        </div>
      </div>
    </div>
    <div class="timeline-wrapper">
      <VideoTrack
        ref="videoTrackRef"
        :enable-main-track-mode="true"
        :track-types="trackTypes"
        :operation-buttons="operationButtons"
        :enable-snap="true"
        :snap-threshold="10"
        :scale-config-buttons="['snap']"
        :thumbnail-height="60"
        :enable-cross-track-drag="true"
        :clip-context-menu="clipContextMenuConfig"
        @clip-context-menu-select="onClipMenuSelect"
        @clip-select="onClipSelect"
        @clip-move="handleClipMove"
        @playback:timeupdate="onTimeUpdate"
        @playback:seek="onCursorSeek"
        @playback:play="onTimelinePlay"
        @playback:pause="onTimelinePause"
        @track-sort="handleTrackSort"
        @dragover="onTimelineDragOver"
        @drop="onTimelineDrop"
      />
    </div>
  </div>

  <!-- =========【在这里粘贴Teleport导出弹窗代码】========= -->
    <Teleport to="body">
      <div v-if="exportDialogVisible" class="export-mask" @click.self="closeExportDialog">
        <div class="export-dialog">
          <div class="dialog-header">
            <span class="title">导出视频</span>
            <span class="close-btn" @click="closeExportDialog">×</span>
          </div>
          <div class="dialog-body">
            <!-- 左侧预览区域 -->
            <div class="preview-col">
              <div class="preview-label">视频首帧预览</div>
              <div class="preview-box">
                <div v-if="exportPreviewImg" class="img-wrap">
                  <img :src="exportPreviewImg" alt="首帧预览" />
                </div>
                <div v-else class="tip-text">
                  首帧加载中…
                </div>
              </div>
            </div>
            <!-- 右侧参数配置 -->
            <div class="setting-col">
              <div class="setting-row">
                <label>格式</label>
                <select v-model="exportOptions.format">
                  <option value="mp4">mp4</option>
                  <option value="webm">webm</option>
                  <option value="mov">mov</option>
                </select>
              </div>
              <div class="setting-row">
                <label>分辨率</label>
                <select v-model="exportOptions.resolution">
                  <option value="1080p">1080p</option>
                  <option value="2k">2k</option>
                  <option value="720p">720p</option>
                  <option value="540p">540p</option>
                  <option value="480p">480p</option>
                  <option value="origin">原始分辨率</option>
                </select>
              </div>
              <div class="setting-row">
                <label>码率</label>
                <select v-model="exportOptions.bitrate">
                  <option value="recommend">推荐</option>
                  <option value="lower">更低</option>
                  <option value="higher">更高</option>
                </select>
              </div>
              <div class="setting-row">
                <label>帧率</label>
                <select v-model="exportOptions.fps">
                  <option value="30">30fps</option>
                  <option value="25">25fps</option>
                  <option value="60">60fps</option>
                </select>
              </div>
              <div class="setting-row">
                <label>编码</label>
                <select v-model="exportOptions.codec">
                  <option value="h264">H.264</option>
                  <option value="h265">H.265</option>
                </select>
              </div>
            </div>
          </div>
          <div class="dialog-footer">
            <button class="btn cancel" @click="closeExportDialog">取消</button>
            <button class="btn primary" @click="handleStartExport">开始导出</button>
          </div>
        </div>
      </div>
    </Teleport>
    <!-- ========= Teleport结束 ========= -->

</template>


<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted, computed,Teleport } from 'vue'
import { VideoTrack, extractVideoThumbnails } from 'vue-clip-track'
import VideoPreview from './components/VideoPreview.vue'
import PropertyPanel from './components/PropertyPanel.vue'

// ===================== 基础状态 =====================
const activeTab = ref('video')
const resourceTabs = [
  { type: 'video', label: ' 视频 ' },
  { type: 'audio', label: ' 音频 ' },
  { type: 'text', label: ' 字幕 ' },
  { type: 'sticker', label: ' 贴纸 ' },
  { type: 'filter', label: ' 滤镜 ' },
  { type: 'effects', label: ' 特效 ' },
  { type: 'transition', label: ' 转场 ' }
]

// 贴纸分类配置
const stickerCategoryList = [
  { key: 'gif', label: '动图' },
  { key: 'bubble', label: '气泡' },
  { key: 'emoji', label: '表情' },
  { key: 'daily', label: '日常' }
]
const activeStickerCat = ref('gif')

// 【新增：滤镜一级分类 + 子滤镜数据】
const filterCategoryList = [
  { key: 'film', label: '胶片' },
  { key: 'fresh', label: '清新' },
  { key: 'travel', label: '旅行' },
  { key: 'art', label: '艺术' }
]
const activeFilterCat = ref('film')

/**
 * filterKey：滤镜唯一标识，给VideoPreview识别滤镜逻辑使用
 * label：UI展示名称
 */
const filterSourceMap: Record<string, Array<{key:string; label:string}>> = {
  film: [
    { key: 'filter-film-retro', label: '复古' },
    { key: 'filter-film-gray', label: '灰调' }
  ],
  fresh: [
    { key: 'filter-fresh-clear', label: '清透' },
    { key: 'filter-fresh-dusk', label: '暮晚' }
  ],
  travel: [
    { key: 'filter-travel-sunny', label: '暖阳' }
  ],
  art: [
    { key: 'filter-art-oil', label: '油画' }
  ]
}
const currentFilterList = computed(() => filterSourceMap[activeFilterCat.value] || [])

// 模拟贴纸资源
const stickerSourceMap: Record<string, Array<{src:string}>> = {
  gif: [
    {src: 'http://localhost:5173/844.gif'},
    {src: 'http://localhost:5173/677.gif'},
    {src: 'http://localhost:5173/717.gif'},
    {src: 'http://localhost:5173/703.gif'},
    {src: 'http://localhost:5173/890.gif'},
    {src: 'http://localhost:5173/919.gif'},
  ],
  bubble: [
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-bubble/46.jpg'},
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-bubble/47.jpg'},
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-bubble/45.jpg'},
  ],
  emoji: [
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-expression/392.jpg'},
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-expression/379.jpg'},
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-expression/542.jpg'},
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-expression/378.jpg'},
  ],
  daily: [
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-daily/147.jpg'},
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-daily/153.jpg'},
    {src: 'https://ice-pub-media.myalicdn.com/public-sticker/sticker-daily/393.jpg'},
  ]
}
const currentStickerList = computed(() => stickerSourceMap[activeStickerCat.value] || [])

// =====================【特效配置 新增】=====================
const effectCategoryList = [
  { key: 'basic', label: '基础' }
]
const activeEffectCat = ref('basic')

/**
 * effectKey：特效唯一标识，VideoPreview识别
 * label：UI展示名称
 */
const effectSourceMap: Record<string, Array<{key:string; label:string}>> = {
  basic: [
    { key: 'open', label: '开幕' },
    { key: 'close', label: '闭幕' },
    { key: 'blur‑gauss', label: '高斯模糊' }
  ]
}
const currentEffectList = computed(() => effectSourceMap[activeEffectCat.value] || [])

// =====================【新增：转场配置】=====================
const transitionCategoryList = [
  { key: 'dissolve', label: '溶解类' },
  { key: 'wipe', label: '擦拭 Wipe' }
]
const activeTransitionCat = ref('dissolve')

type TransitionType = 'dissolve' | 'cross-dissolve' | 'dip-to-black' | 'dip-to-white'
const transitionSourceMap: Record<string, Array<{key:TransitionType; label:string}>> = {
  dissolve: [
    { key: 'dissolve', label: '基础溶解' },
    { key: 'cross-dissolve', label: '交叉溶解' }
  ],
  wipe: [
    { key: 'wipe-left', label: '向左擦拭' },
    { key: 'wipe-right', label: '向右擦拭' }
  ]
}
const currentTransitionList = computed(() => transitionSourceMap[activeTransitionCat.value] || [])


// 素材库
const materialStore = ref({
  video: [],
  audio: [],
  image: [],
  text: [],
  sticker: [],
  filter: []
})

// 时间轴数据
const trackData = ref({
  tracks: []
})

// 轨道类型配置【新增 filter】
const trackTypes = ref({
  video: { max: 10 },
  audio: { max: 10 },
  sticker: { max: 15 },
  subtitle: { max: 10 },
  filter: { max: 8 },
  effect: { max:8 },
  transition: { max: 8 }
})

const operationButtons = [
  'reset',   // 重置
  'undo',    // 撤销
  'redo',    // 重做
  'split',   // 分割素材
  'delete'   // 删除
]

// 拆分两个文件输入框
const videoFileInput = ref(null)
const audioFileInput = ref(null)

const currentTime = ref(0)
const selectedClip = ref(null)
const videoTrackRef = ref(null)
const previewRef = ref(null)
let lockMove = false

// ===================== 素材 Tab 筛选 =====================
const getMaterialList = () => materialStore.value[activeTab.value] || []

// =========简易toast轻提示，自动消失，挂载body==========
function showToast(message: string, duration = 2500) {
  const div = document.createElement('div')
  div.innerText = message
  div.style.cssText = `
    position:fixed;
    left:50%;
    top:5%;
    transform:translate(-50%,-50%);
    background:rgba(0,0,0,0.75);
    color:#fff;
    padding:10px 18px;
    border-radius:6px;
    z-index:99999;
    pointer-events:none;
    font-size:14px;
  `
  document.body.appendChild(div)
  setTimeout(() => {
    div.style.opacity = '0'
    div.style.transition = 'opacity 0.3s'
    setTimeout(() => div.remove(), 300)
  }, duration)
}

// ==========导出弹窗相关状态==========
const exportDialogVisible = ref(false)
const exportPreviewImg = ref('')
const exportOptions = ref({
  format: 'mp4',
  resolution: '1080p',
  bitrate: 'recommend',
  fps: '30',
  codec: 'h264'
})

/** 获取轨道上第一个可显示的视频clip */
function getFirstVideoClip() {
  if (!videoTrackRef.value) return null
  const allTracks = videoTrackRef.value.getTracks()
  for (const track of allTracks) {
    if (!track.visible) continue
    for (const clip of track.clips) {
      if (clip.type === 'video') {
        return clip
      }
    }
  }
  return null
}

// ===== 拖拽素材 =====
let dragMaterial:any = null
let dragSticker:any = null

function handleMaterialDragStart(e:DragEvent, item:any){
  dragMaterial = item
  dragSticker = null
  e.dataTransfer!.effectAllowed = "copy"
}
function handleStickerDragStart(e:DragEvent, sticker:any){
  dragSticker = sticker
  dragMaterial = null
  e.dataTransfer!.effectAllowed = "copy"
}

function onTimelineDragOver(e:DragEvent){
  e.preventDefault()
}

/**
 * VideoTrack drop事件，拿到释放位置时间戳
 */
async function onTimelineDrop(e: DragEvent){
  e.preventDefault() // drop内部也要preventDefault，防止浏览器打开文件
  const dropTime = currentTime.value
  if(dragMaterial){
    // 视频/音频素材
    const mat = dragMaterial
    const cursorBackup = currentTime.value
    currentTime.value = dropTime
    await addMaterialToTrack(mat)
    currentTime.value = cursorBackup
    dragMaterial = null
  }else if(dragSticker){
    // 贴纸素材
    const stk = dragSticker
    const cursorBackup = currentTime.value
    currentTime.value = dropTime
    await addStickerToTrack(stk)
    currentTime.value = cursorBackup
    dragSticker = null
  }
}

/** 根据视频url截取第一帧返回base64图片 */
async function captureVideoFirstFrame(videoSrc: string): Promise<string> {
  return new Promise((resolve) => {
    const video = document.createElement('video')
    video.crossOrigin = 'anonymous'
    video.preload = 'auto'
    video.src = videoSrc
    video.muted = true
    video.currentTime = 0.1
    video.onloadeddata = () => {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')
      ctx!.drawImage(video, 0, 0)
      const base64 = canvas.toDataURL('image/jpeg', 0.8)
      video.remove()
      canvas.remove()
      resolve(base64)
    }
    video.onerror = () => {
      video.remove()
      resolve('')
    }
  })
}

/** 打开导出弹窗 */
async function openExportDialog() {
  const firstVideoClip = getFirstVideoClip()

  if (!firstVideoClip) {
    showToast('当前创作轨道无有效素材，请添加素材后再发起合成。')
    return
  }
  exportDialogVisible.value = true
  exportPreviewImg.value = ''
  // 截取首帧
  const base64Img = await captureVideoFirstFrame(firstVideoClip.source)
  exportPreviewImg.value = base64Img

}

function closeExportDialog() {
  exportDialogVisible.value = false
}

/**
 * 上传单个blob url到后端，返回后端资源url
 * @param blobUrl blob:http://xxx
 */
async function uploadBlobSource(blobUrl: string): Promise<string> {
  const resp = await fetch(blobUrl);
  const blob = await resp.blob();

  const formData = new FormData();
  formData.append("mediaFile", blob, "temp_media");

  const uploadRes = await fetch("http://127.0.0.1:8095/api/media/upload-blob", {
    method: "POST",
    body: formData
  });
  const json = await uploadRes.json();
  if (!json.success) {
    throw new Error(json.msg || "blob上传失败");
  }
  return json.resourceUrl;
}

/** 遍历轨道，把所有blob://的source全部上传替换 */
async function replaceAllBlobSources(tracks: any[]) {
  // 收集所有需要上传的clip
  const todoList: Array<{ trackIdx: number; clipIdx: number; blobUrl: string }> = [];
  tracks.forEach((track, trackIdx) => {
    track.clips.forEach((clip: any, clipIdx: number) => {
      const src = clip.source;
      if (src && typeof src === "string" && src.startsWith("blob:")) {
        todoList.push({ trackIdx, clipIdx, blobUrl: src });
      }
    });
  });

  if (todoList.length === 0) return tracks;

  showToast(`检测到${todoList.length}个blob素材，正在上传…`);

  // 顺序串行上传，防止并发过高
  for (const item of todoList) {
    const newUrl = await uploadBlobSource(item.blobUrl);
    const track = tracks[item.trackIdx];
    track.clips[item.clipIdx].source = newUrl;

    console.log('-----------newUrl--',newUrl)

  }
  return tracks;
}

/** 开始导出 */
async function handleStartExport() {
  if (!getFirstVideoClip()) {
    alert('当前创作轨道无有效素材，请添加素材后再发起合成。')
    return
  }
  closeExportDialog()
  showToast("开始提交导出任务，请稍候…")

  console.log('-------------a')

  const exportTracks = JSON.parse(JSON.stringify(trackData.value.tracks));
  await replaceAllBlobSources(exportTracks);

  // ========== 新增：subtitle字幕换行符替换 \n → \\N 适配ffmpeg drawtext ==========
  for(const track of exportTracks){
    for(const clip of track.clips){
      if(clip.type === 'subtitle' && typeof clip.text === 'string'){
        clip.text = clip.text.replaceAll('\n','\\N')
      }
    }
  }

  const payload = {
    exportOptions: { ...exportOptions.value },
    tracks: exportTracks
  }

  try {
    const resp = await fetch("http://127.0.0.1:8095/api/export/render", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    })
    const res = await resp.json()
    if(!res.success){
      showToast(`任务提交失败：${res.msg}`)
      return
    }
    const taskId = res.taskId
    // 轮询查询进度
    const pollTimer = setInterval(async ()=>{
      const statResp = await fetch(`http://127.0.0.1:8095/api/export/status?taskId=${taskId}`)
      const stat = await statResp.json()
      if(!stat.success){
        clearInterval(pollTimer)
        showToast("查询任务失败")
        return
      }
      showToast(`渲染进度：${stat.progress}%`)
      if(stat.status === 'finished'){
        clearInterval(pollTimer)
        showToast(`渲染完成！${stat.downloadUrl}`)
        console.log('渲染完成！-----',stat.downloadUrl)
        //window.open(stat.downloadUrl)
      }else if(stat.status === 'failed'){
        clearInterval(pollTimer)
        showToast(`渲染失败:${stat.errorMsg}`)
      }
    },1000)

  } catch(err: any) {
    console.error(err)
    showToast("导出异常：" + (err?.message || String(err)))
  }
}


// 导入视频素材
const handleSelectVideo = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0) return

  const MAX_SIZE = 50 * 1024 * 1024 // 50MB
  const overFiles: File[] = []
  const validFiles: File[] = []

  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (file.size > MAX_SIZE) {
      overFiles.push(file)
    } else {
      validFiles.push(file)
    }
  }

  if (overFiles.length) {
    const names = overFiles.map(f => f.name).join('、')
    alert(`以下文件超过50MB限制：${names}`)
  }

  if (validFiles.length === 0) {
    target.value = ''
    return
  }

  for (let i = 0; i < validFiles.length; i++) {
    const file = validFiles[i]
    const videoUrl = URL.createObjectURL(file)

    const cover = await captureVideoCover(videoUrl)
    const meta = await getVideoMeta(videoUrl)
    const duration = meta.duration
    const width = meta.width
    const height = meta.height

    const newVideoItem = {
      id: `mat-${Date.now()}-${i}`,
      name: file.name,
      source: videoUrl,
      duration,
      naturalWidth: meta.width,
      naturalHeight: meta.height,
      materialType: 'video',
      cover
    }

    materialStore.value.video.push(newVideoItem)
  }

  target.value = ''
}

// 导入音频素材
const handleSelectAudio = async (e: Event) => {
  const target = e.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0) return

  const MAX_SIZE = 10 * 1024 * 1024 // 10MB
  const overFiles: File[] = []
  const validFiles: File[] = []

  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (file.size > MAX_SIZE) {
      overFiles.push(file)
    } else {
      validFiles.push(file)
    }
  }

  if (overFiles.length) {
    const names = overFiles.map(f => f.name).join('、')
    alert(`以下音频文件超过10MB限制：${names}`)
  }

  if (validFiles.length === 0) {
    target.value = ''
    return
  }

  for (let i = 0; i < validFiles.length; i++) {
    const file = validFiles[i]
    const audioUrl = URL.createObjectURL(file)
    const duration = await getAudioDuration(audioUrl)

    const newAudioItem = {
      id: `mat-audio-${Date.now()}-${i}`,
      name: file.name,
      source: audioUrl,
      duration,
      materialType: 'audio',
      cover: ''
    }
    materialStore.value.audio.push(newAudioItem)
  }

  target.value = ''
}

// 获取音频时长
function getAudioDuration(url: string): Promise<number> {
  return new Promise((resolve) => {
    const audio = new Audio(url)
    audio.addEventListener('loadedmetadata', () => {
      resolve(audio.duration)
      audio.remove()
    })
    audio.addEventListener('error', () => {
      resolve(0)
      audio.remove()
    })
  })
}

const clipContextMenuConfig = {
  showCommonItems: false,
  byType: {
    video: [
      { key: 'copy', label: ' 复制 ', icon: '📋' },
      { key: 'cut', label: ' 剪切 ', icon: '✂️' },
      { key: 'splitAudio', label: ' 分离音轨 ', icon: '🔊' },
      { key: 'delete', label: ' 删除 ', icon: '🗑️' }
    ],
    audio: [
      { key: 'copy', label: ' 复制 ', icon: '📋' },
      { key: 'cut', label: ' 剪切 ', icon: '✂️' },
      { key: 'delete', label: ' 删除 ', icon: '🗑️' }
    ],
    sticker: [
      { key: 'copy', label: ' 复制 ', icon: '📋' },
      { key: 'cut', label: ' 剪切 ', icon: '✂️' },
      { key: 'delete', label: ' 删除 ', icon: '🗑️' }
    ],
    subtitle: [
      { key: 'copy', label: ' 复制 ', icon: '📋' },
      { key: 'cut', label: ' 剪切 ', icon: '✂️' },
      { key: 'delete', label: ' 删除 ', icon: '🗑️' }
    ],
    filter: [
      { key: 'copy', label: ' 复制 ', icon: '📋' },
      { key: 'cut', label: ' 剪切 ', icon: '✂️' },
      { key: 'delete', label: ' 删除 ', icon: '🗑️' }
    ],
    effect: [
      { key: 'copy', label: ' 复制 ', icon: '📋' },
      { key: 'cut', label: ' 剪切 ', icon: '✂️' },
      { key: 'delete', label: ' 删除 ', icon: '🗑️' }
    ],
    transition: [
      { key: 'copy', label: ' 复制 ', icon: '📋' },
      { key: 'cut', label: ' 剪切 ', icon: '✂️' },
      { key: 'delete', label: ' 删除 ', icon: '🗑️' }
    ]
  },
  extraItems: []
};

function onClipMenuSelect(menuKey, clip) {
  switch (menuKey) {
    case 'splitAudio':
      handleSplitAudio({ clip })
      break;
  }
}

async function handleSplitAudio({ clip }) {
  if (clip.hasSplitAudio === true) {
    alert("该视频已经分离过音频，请勿重复分离！");
    return;
  }

  try {
    console.log(' 开始分离音轨 clip:', clip)
    const resData = await uploadBlobToBackend(clip.source)
    if (!resData.success || !resData.audioUrl || !Array.isArray(resData.waveform)) {
      throw new Error(' 后端未返回音频地址或波形数据 ')
    }

    const audioSourceUrl = resData.audioUrl
    const waveformData = resData.waveform

    const allTracks = videoTrackRef.value.getTracks()
    const audioTracks = allTracks.filter(t => t.type === 'audio')
    const maxOrderAll = allTracks.reduce((max, t) => Math.max(max, t.order ?? 0), -1)

    const audioTrackNum = audioTracks.length + 1
    const newAudioTrack = {
      id: `audio-track-${Date.now()}`,
      type: 'audio',
      name: `音频${audioTrackNum}`,
      mainTrack: false,
      visible: true,
      locked: false,
      order: maxOrderAll + 1,
      clips: []
    }

    const audioClip = {
      id: `clip-audio-${Date.now()}`,
      type: 'audio',
      name: `${clip.name} - 音频`,
      startTime: clip.startTime,
      endTime: clip.endTime,
      source: audioSourceUrl,
      sourceStartTime: clip.sourceStartTime,
      sourceEndTime: clip.sourceEndTime,
      originalDuration: clip.originalDuration,
      trimStart: clip.trimStart,
      trimEnd: clip.trimEnd,
      transform: { x: 0, y: 0, scale: 1 },
      naturalWidth: 0,
      naturalHeight: 0,
      thumbnails: [],
      waveformData: waveformData
    }

    newAudioTrack.clips.push(audioClip)
    videoTrackRef.value.addTrack(newAudioTrack)

    clip.hasSplitAudio = true;
    videoTrackRef.value.updateClip(clip.id, { hasSplitAudio: true });

    await nextTick()
    handleTrackSort()
    syncAllTracks()

  } catch (err) {
    console.error(' 音轨提取失败：', err)
    alert(' 音轨分离失败！')
  }
}

async function uploadBlobToBackend(blobVideoUrl) {
  const res = await fetch(blobVideoUrl);
  const blob = await res.blob();

  const formData = new FormData();
  formData.append("video", blob, "temp.mp4");

  const resp = await fetch("http://127.0.0.1:8095/api/media/extract-audio", {
    method: "POST",
    body: formData
  });
  return await resp.json();
}

function getVideoMeta(url: string): Promise<{ duration: number; width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.src = url

    video.onloadedmetadata = () => {
      const meta = {
        duration: Math.floor(video.duration),
        width: video.videoWidth,
        height: video.videoHeight
      }
      video.remove()
      resolve(meta)
    }

    video.onerror = (err) => {
      video.remove()
      reject(err)
    }
  })
}

function captureVideoCover(videoUrl: string): Promise<string> {
  return new Promise((resolve) => {
    const video = document.createElement('video')
    video.src = videoUrl
    video.muted = true
    video.preload = 'metadata'

    video.onloadedmetadata = () => {
      video.currentTime = Math.min(0.3, video.duration - 0.1)
    }

    video.onseeked = () => {
      const canvas = document.createElement('canvas')
      const width = 160
      const scale = width / video.videoWidth
      canvas.width = width
      canvas.height = video.videoHeight * scale
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const base64 = canvas.toDataURL('image/jpeg', 0.6)
      video.remove()
      canvas.remove()
      resolve(base64)
    }

    video.onerror = () => {
      video.remove()
      resolve('')
    }
  })
}

const deleteMaterial = (materialId: string) => {
  const key = activeTab.value
  materialStore.value[key] = materialStore.value[key].filter(
    m => m.id !== materialId
  )
}

// =====================【新增：添加转场】=====================
const TRANSITION_DEFAULT_DURATION = 1 // 默认转场时长 1s
interface TransitionClip {
  id: string
  type: 'transition'
  name: string
  transitionType: string
  duration: number
  startTime: number
  endTime: number
}

const addTransitionToTrack = async (transItem: {key:TransitionType; label:string}) => {
  // 校验1：必须选中clip
  if (!selectedClip.value) {
    alert('请先选中一段视频素材！')
    return
  }
  const sourceClip = selectedClip.value
  // 校验2：选中片段类型必须是视频
  if (sourceClip.type !== 'video') {
    alert('转场仅支持添加在视频片段后方！')
    return
  }
  const clipEndTime = sourceClip.endTime

  const trackList = videoTrackRef.value.getTracks()
  // 找到该视频所在轨道
  const parentTrack = trackList.find(t => t.clips.some(c => c.id === sourceClip.id))
  if (!parentTrack) return

  // 校验3：在同一条视频轨道，查找【起始时间 = 当前片段结束时间】的下一段视频
  const nextVideoClip = parentTrack.clips.find(c => {
    return c.type === 'video' && Math.abs(c.startTime - clipEndTime) < 0.08
  })
  if (!nextVideoClip) {
    alert('当前视频后方没有相邻视频片段，无法添加转场！\n请在当前视频尾部拼接下一段视频。')
    return
  }

  // 转场区间：前视频末尾和后视频开头重叠
  const transStart = clipEndTime - TRANSITION_DEFAULT_DURATION
  const transEnd = clipEndTime
  // 🛡边界保护：转场开始不能小于0，也不能小于源视频的起始时间，不能把转场伸到源视频前面
  const safeTransStart = Math.max(0, sourceClip.startTime, transStart)

  // 构建TransitionClip对象
  const newTransitionClip: TransitionClip = {
    id: `clip-transition-${Date.now()}`,
    type: 'transition',
    name: transItem.label,
    transitionType: transItem.key,
    duration: TRANSITION_DEFAULT_DURATION,
    startTime: safeTransStart,
    endTime: transEnd
  }

  // 寻找/新建转场轨道
  const cursorTime = currentTime.value
  const trackType = 'transition'
  const tracks_list = videoTrackRef.value.getTracks()
  let sameTypeTracks = tracks_list.filter(t => t.type === trackType)

  const maxOrder = tracks_list.reduce((max, track) => Math.max(max, track.order ?? 0), -1)
  let targetTrack = null
  let isNewTrack = false

  let maxIndex = 0
  const reg = new RegExp(`^(转场)(\\d+)$`)
  sameTypeTracks.forEach(track => {
    const match = track.name.match(reg)
    if (match) {
      const num = parseInt(match[2],10)
      if(num>maxIndex) maxIndex = num
    }
  })
  const nextIndex = maxIndex + 1

  if (sameTypeTracks.length === 0) {
    targetTrack = {
      id: `${trackType}-${Date.now()}`,
      type: trackType,
      name: `转场${nextIndex}`,
      mainTrack: false,
      visible: true,
      locked: false,
      order: maxOrder + 1,
      clips: []
    }
    isNewTrack = true
  } else {
    for(const track of sameTypeTracks){
      const isFreeTrack = track.clips.every(clip=>clip.endTime <= cursorTime)
      if(isFreeTrack){
        targetTrack = track
        break
      }
    }
    if(!targetTrack){
      targetTrack = {
        id: `${trackType}-${Date.now()}`,
        type: trackType,
        name: `转场${nextIndex}`,
        mainTrack: false,
        visible: true,
        locked: false,
        order: maxOrder + 1,
        clips: []
      }
      isNewTrack = true
    }
  }

  if(isNewTrack){
    targetTrack.clips.push(newTransitionClip)
    videoTrackRef.value.addTrack(targetTrack)
  }else{
    videoTrackRef.value.addClip(targetTrack.id, newTransitionClip)
  }
  await nextTick()
  handleTrackSort()
  syncAllTracks()
  onClipSelect(newTransitionClip)
}


// ===================== 贴纸添加核心方法 =====================
const addStickerToTrack = async (stickerItem: {src:string}) => {
  const cursorTime = currentTime.value
  const STICKER_DURATION = 5 // 默认5秒
  const trackType = 'sticker'

  const tracks_list = videoTrackRef.value.getTracks()
  let sameTypeTracks = tracks_list.filter(t => t.type === trackType)

  const maxOrder = tracks_list.reduce((max, track) => Math.max(max, track.order ?? 0), -1)
  let targetTrack = null
  let isNewTrack = false

  let maxIndex = 0
  const reg = new RegExp(`^(贴纸)(\\d+)$`)
  sameTypeTracks.forEach(track => {
    const match = track.name.match(reg)
    if (match) {
      const num = parseInt(match[2], 10)
      if (num > maxIndex) maxIndex = num
    }
  })
  const nextIndex = maxIndex + 1

  if (sameTypeTracks.length === 0) {
    targetTrack = {
      id: `${trackType}-${Date.now()}`,
      type: trackType,
      name: `贴纸${nextIndex}`,
      mainTrack: false,
      visible: true,
      locked: false,
      order: maxOrder + 1,
      clips: []
    }
    isNewTrack = true
  } else {
    for (const track of sameTypeTracks) {
      const isFreeTrack = track.clips.every(clip => clip.endTime <= cursorTime)
      if (isFreeTrack) {
        targetTrack = track
        break
      }
    }
    if (!targetTrack) {
      targetTrack = {
        id: `${trackType}-${Date.now()}`,
        type: trackType,
        name: `贴纸${nextIndex}`,
        mainTrack: false,
        visible: true,
        locked: false,
        order: maxOrder + 1,
        clips: []
      }
      isNewTrack = true
    }
  }

  // 构建贴纸片段（和VideoPreview渲染结构对齐）
  const newClip = {
    id: `clip-sticker-${Date.now()}`,
    type: 'sticker',
    name: '贴纸',
    startTime: cursorTime,
    endTime: cursorTime + STICKER_DURATION,
    source: stickerItem.src,
    sourceStartTime: 0,
    sourceEndTime: STICKER_DURATION,
    originalDuration: STICKER_DURATION,
    trimStart: 0,
    trimEnd: STICKER_DURATION,
    transform: {
      x: 783/2,
      y: 450/2,
      scale: 0.2
    },
    rotate: 0,
    opacity: 1,
    naturalWidth: 60,
    naturalHeight: 60,
    thumbnails: [],
    waveformData: []
  }

  if (isNewTrack) {
    targetTrack.clips.push(newClip)
    videoTrackRef.value.addTrack(targetTrack)
  } else {
    videoTrackRef.value.addClip(targetTrack.id, newClip)
  }

  await nextTick()
  handleTrackSort()
  syncAllTracks()
  onClipSelect(newClip)
}

// =====================【新增：添加滤镜到轨道】=====================
const addFilterToTrack = async (filterItem: {key:string; label:string}) => {
  const cursorTime = currentTime.value
  const FILTER_DURATION = 5
  const trackType = 'filter'

  const tracks_list = videoTrackRef.value.getTracks()
  let sameTypeTracks = tracks_list.filter(t => t.type === trackType)

  const maxOrder = tracks_list.reduce((max, track) => Math.max(max, track.order ?? 0), -1)
  let targetTrack = null
  let isNewTrack = false

  let maxIndex = 0
  const reg = new RegExp(`^(滤镜)(\\d+)$`)
  sameTypeTracks.forEach(track => {
    const match = track.name.match(reg)
    if (match) {
      const num = parseInt(match[2],10)
      if(num>maxIndex) maxIndex = num
    }
  })
  const nextIndex = maxIndex + 1

  if (sameTypeTracks.length === 0) {
    targetTrack = {
      id: `${trackType}-${Date.now()}`,
      type: trackType,
      name: `滤镜${nextIndex}`,
      mainTrack: false,
      visible: true,
      locked: false,
      order: maxOrder + 1,
      clips: []
    }
    isNewTrack = true
  } else {
    for(const track of sameTypeTracks){
      const isFreeTrack = track.clips.every(clip=>clip.endTime <= cursorTime)
      if(isFreeTrack){
        targetTrack = track
        break
      }
    }
    if(!targetTrack){
      targetTrack = {
        id: `${trackType}-${Date.now()}`,
        type: trackType,
        name: `滤镜${nextIndex}`,
        mainTrack: false,
        visible: true,
        locked: false,
        order: maxOrder + 1,
        clips: []
      }
      isNewTrack = true
    }
  }

  // filter类型clip，供PropertyPanel、VideoPreview读取
  const newClip = {
    id: `clip-filter-${Date.now()}`,
    type: 'filter',
    name: filterItem.label,
    startTime: cursorTime,
    endTime: cursorTime + FILTER_DURATION,
    source: '',
    sourceStartTime: 0,
    sourceEndTime: FILTER_DURATION,
    originalDuration: FILTER_DURATION,
    trimStart: 0,
    trimEnd: FILTER_DURATION,
    transform: { x:0,y:0,scale:1 },
    // 滤镜核心字段，VideoPreview读取
    filterKey: filterItem.key,
    filterLabel: filterItem.label,
    intensity: 0.7, // 滤镜强度 0‑1
    thumbnails: [],
    waveformData: []
  }

  if(isNewTrack){
    targetTrack.clips.push(newClip)
    videoTrackRef.value.addTrack(targetTrack)
  }else{
    videoTrackRef.value.addClip(targetTrack.id, newClip)
  }
  await nextTick()
  handleTrackSort()
  syncAllTracks()
  onClipSelect(newClip)
}

// =====================【新增：添加特效到轨道】=====================
const addEffectToTrack = async (effectItem: {key:string; label:string}) => {
  const cursorTime = currentTime.value
  const EFFECT_DURATION = 5
  const trackType = 'effect'

  const tracks_list = videoTrackRef.value.getTracks()
  let sameTypeTracks = tracks_list.filter(t => t.type === trackType)

  const maxOrder = tracks_list.reduce((max, track) => Math.max(max, track.order ?? 0), -1)
  let targetTrack = null
  let isNewTrack = false

  let maxIndex = 0
  const reg = new RegExp(`^(特效)(\\d+)$`)
  sameTypeTracks.forEach(track => {
    const match = track.name.match(reg)
    if (match) {
      const num = parseInt(match[2],10)
      if(num>maxIndex) maxIndex = num
    }
  })
  const nextIndex = maxIndex + 1

  if (sameTypeTracks.length === 0) {
    targetTrack = {
      id: `${trackType}-${Date.now()}`,
      type: trackType,
      name: `特效${nextIndex}`,
      mainTrack: false,
      visible: true,
      locked: false,
      order: maxOrder + 1,
      clips: []
    }
    isNewTrack = true
  } else {
    for(const track of sameTypeTracks){
      const isFreeTrack = track.clips.every(clip=>clip.endTime <= cursorTime)
      if(isFreeTrack){
        targetTrack = track
        break
      }
    }
    if(!targetTrack){
      targetTrack = {
        id: `${trackType}-${Date.now()}`,
        type: trackType,
        name: `特效${nextIndex}`,
        mainTrack: false,
        visible: true,
        locked: false,
        order: maxOrder + 1,
        clips: []
      }
      isNewTrack = true
    }
  }

  const newClip = {
    id: `clip-effect-${Date.now()}`,
    type: 'effect',
    name: effectItem.label,
    startTime: cursorTime,
    endTime: cursorTime + EFFECT_DURATION,
    source: '',
    sourceStartTime: 0,
    sourceEndTime: EFFECT_DURATION,
    originalDuration: EFFECT_DURATION,
    trimStart: 0,
    trimEnd: EFFECT_DURATION,
    transform: { x:0,y:0,scale:1 },
    // 特效核心字段
    effectKey: effectItem.key,
    effectLabel: effectItem.label,
    intensity: 1.0,
    thumbnails: [],
    waveformData: []
  }

  if(isNewTrack){
    targetTrack.clips.push(newClip)
    videoTrackRef.value.addTrack(targetTrack)
  }else{
    videoTrackRef.value.addClip(targetTrack.id, newClip)
  }
  await nextTick()
  handleTrackSort()
  syncAllTracks()
  onClipSelect(newClip)
}


// =====================【核心修改：无震荡时间同步逻辑】=====================
const onPreviewTimeUpdate = (time: number) => {
  currentTime.value = time
}

const onPreviewSeeked = (time: number) => {
}

const saveTrackDate = () => {
  const data = videoTrackRef.value.exportData()
  console.log('----------', data)
}

// 素材点击添加到时间轴
const addMaterialToTrack = async (material) => {
  const cursorTime = currentTime.value
  const trackType = material.materialType

  const tracks_list = videoTrackRef.value.getTracks()
  let sameTypeTracks = tracks_list.filter(t => t.type === trackType)

  const maxOrder = tracks_list.reduce((max, track) => Math.max(max, track.order ?? 0), -1)

  let targetTrack = null
  let isNewTrack = false

  let maxIndex = 0
  const reg = new RegExp(`^(视频|音频)(\\d+)$`)
  sameTypeTracks.forEach(track => {
    const match = track.name.match(reg)
    if (match) {
      const num = parseInt(match[2], 10)
      if (num > maxIndex) maxIndex = num
    }
  })
  const nextIndex = maxIndex + 1

  if (sameTypeTracks.length === 0) {
    targetTrack = {
      id: `${trackType}-${Date.now()}`,
      type: trackType,
      name: `${trackType === 'video' ? '视频' : '音频'}${nextIndex}`,
      mainTrack: trackType === 'video',
      visible: true,
      locked: false,
      order: maxOrder + 1,
      clips: []
    }
    isNewTrack = true
  } else {
    for (const track of sameTypeTracks) {
      const isFreeTrack = track.clips.every(clip => clip.endTime <= cursorTime)
      if (isFreeTrack) {
        targetTrack = track
        break
      }
    }
    if (!targetTrack) {
      targetTrack = {
        id: `${trackType}-${Date.now()}`,
        type: trackType,
        name: `${trackType === 'video' ? '视频' : '音频'}${nextIndex}`,
        mainTrack: trackType === 'video',
        visible: true,
        locked: false,
        order: maxOrder + 1,
        clips: []
      }
      isNewTrack = true
    }
  }

  let thumbnails_list = []
  let waveformData = []
  if (material.materialType === 'video') {
    thumbnails_list = await extractVideoThumbnails(material.source, Math.floor(Number(material.duration)))
    thumbnails_list = thumbnails_list.thumbnails
  } else if (material.materialType === 'audio') {
    waveformData = await uploadBlobAudio(material.source)
    waveformData = waveformData.waveform
  }

  const newClip = {
    id: `clip-${Date.now()}`,
    type: material.materialType,
    name: material.name,
    startTime: cursorTime,
    endTime: cursorTime + material.duration,
    source: material.source,
    sourceStartTime: 0,
    sourceEndTime: material.duration,
    originalDuration: material.duration,
    trimStart: 0,
    trimEnd: material.duration,
    opacity: 1,
    transform: {
      x: 783/2,
      y: 450/2,
      scale: 1
    },
    naturalWidth: material.naturalWidth ?? 0,
    naturalHeight: material.naturalHeight ?? 0,
    thumbnails: thumbnails_list,
    waveformData: waveformData
  }

  console.log('=======newClip==',newClip)

  if (isNewTrack) {
    targetTrack.clips.push(newClip)
    videoTrackRef.value.addTrack(targetTrack)
  } else {
    videoTrackRef.value.addClip(targetTrack.id, newClip)
  }

  await nextTick()
  handleTrackSort()
  syncAllTracks()
  // =========新增：添加素材后，通知预览组件强制刷新当前时间，触发视频初始化加载+全量绘制========
  if(previewRef.value){
    await previewRef.value.setCurrentTime(currentTime.value, true)
  }
  onClipSelect(newClip)
}

async function uploadBlobAudio(blobUrl) {
  const res = await fetch(blobUrl);
  const blob = await res.blob();

  let ext = "aac";
  const mime = blob.type;
  if (mime.includes("mpeg")) ext = "mp3";
  else if (mime.includes("wav")) ext = "wav";
  else if (mime.includes("aac")) ext = "aac";
  else if (mime.includes("aac")) ext = "wma";

  const formData = new FormData();
  formData.append("audio", blob, `audio.${ext}`);
  const uploadRes = await fetch("http://127.0.0.1:8095/api/media/getAudioWaveform", {
    method: "POST",
    body: formData
  });
  const data = await uploadRes.json();
  if (!data.success) throw new Error("音频解析失败");
  return {
    waveform: data.waveform
  };
}

const syncAllTracks = () => {
  if (!videoTrackRef.value) return
  const timelineTracks = videoTrackRef.value.getTracks()
  trackData.value.tracks = [...timelineTracks]
}

watch(
  () => videoTrackRef.value?.getTracks() || [],
  async () => {
    await nextTick()
    const tracks = videoTrackRef.value?.getTracks() ?? []
    tracks.forEach(track => {
      if (track.id.startsWith('track-')) {
        //videoTrackRef.value?.removeTrack(track.id)
      }
    })
  },
  { deep: true }
)

// 监听选中clip，当trackData内部该clip的数据被修剪/修改时，自动刷新selectedClip，同步属性面板
watch(
  selectedClip,
  (newVal) => {
    if (!newVal?.id) return;
    const clipId = newVal.id;
    // 深度监听整个轨道数据，当对应clip的startTime/endTime改变，重新拉取最新对象
    const unwatchTrack = watch(
      () => trackData.value.tracks,
      () => {
        if (!videoTrackRef.value) return;
        const freshClip = videoTrackRef.value.getClipById(clipId);
        if (!freshClip) {
          unwatchTrack();
          return;
        }
        // 对象引用不一样，说明数据发生了修剪/变更
        if (freshClip !== selectedClip.value) {
          selectedClip.value = freshClip;
        }
      },
      { deep: true }
    );
  },
  { immediate: false }
);

let pollTimer = null
let cacheTrackCount = 0

onMounted(() => {
  if (!videoTrackRef.value) return
  const initTracks = videoTrackRef.value.getTracks()
  cacheTrackCount = initTracks.length

  pollTimer = setInterval(() => {
    const tracks = videoTrackRef.value.getTracks()
    if (tracks.length !== cacheTrackCount) {
      cacheTrackCount = tracks.length
      syncAllTracks()
    }
  }, 200)
})
onUnmounted(() => {
  clearInterval(pollTimer)
})

// ===================== 时间轴事件 =====================
const onTimeUpdate = (time) => {
  currentTime.value = time
  previewRef.value?.setCurrentTime(time, false)
}

const onCursorSeek = (time) => {
  currentTime.value = time
  previewRef.value?.setCurrentTime(time, true)
  lockMove = true
  setTimeout(() => { lockMove = false }, 100)
}

const handleTrackSort = async () => {
  await nextTick()
  const uiTrackList = videoTrackRef.value!.getSortedTracks()
  uiTrackList.forEach((track, index) => {
    const order = uiTrackList.length - 1 - index
    videoTrackRef.value!.updateTrack(track.id, { order })
  })
}

let isSyncing = false
const onTimelinePlay = () => {
  if (isSyncing) return
  isSyncing = true
  previewRef.value?.play()
  videoTrackRef.value?.play()
  setTimeout(() => isSyncing = false, 150)
}
const onTimelinePause = () => {
  if (isSyncing) return
  isSyncing = true
  previewRef.value?.pause()
  videoTrackRef.value?.pause()
  setTimeout(() => isSyncing = false, 150)
}

const onPreviewPlay = () => {
  if (isSyncing) return
  isSyncing = true
  videoTrackRef.value?.play()
  setTimeout(() => isSyncing = false, 150)
}
const onPreviewPause = () => {
  if (isSyncing) return
  isSyncing = true
  videoTrackRef.value?.pause()
  setTimeout(() => isSyncing = false, 150)
}

const onClipSelect = (payload) => {
  let fullClip = null
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    fullClip = payload
  } else if (Array.isArray(payload)) {
    const clipId = payload[0]
    if (clipId) {
      fullClip = videoTrackRef.value.getClipById(clipId)
    }
  }
  selectedClip.value = fullClip
  console.log(' 选中完整片段：', fullClip)
}

// --------------------------【修改这里：实现handleClipMove】--------------------------
/**
 * @param clipId 被拖动/拉伸的片段id
 * @param trackId 目标轨道id
 * @param newStart 新的startTime
 */
const handleClipMove = async (clipId, trackId, newStart) => {
  // 时间轴拖动、拉伸结束之后，读取最新clip对象
  await nextTick();
  const latestClip = videoTrackRef.value.getClipById(clipId);
  if (!latestClip) return;

  // 更新轨道数据
  syncAllTracks();
  // 把最新clip赋值给selectedClip，PropertyPanel拿到新对象，面板刷新
  selectedClip.value = latestClip;
  // 通知预览组件更新clip
  handleClipPropUpdate(latestClip);
}

const handleClipPropUpdate = (newClip, changedKey?: string) => {
  console.log('修改的属性：', changedKey) // 这里就能拿到是哪个属性！
  if (!videoTrackRef.value) return
  if (changedKey === 'playbackRate') {
    videoTrackRef.value.setClipPlaybackRate(newClip.id, newClip.playbackRate)
  } else {
    videoTrackRef.value.updateClip(newClip.id, { ...newClip })
  }
  syncAllTracks()
  const latestClip = videoTrackRef.value.getClipById(newClip.id)
  selectedClip.value = latestClip
}

// 添加字幕到时间轴
const addSubtitleToTrack = async () => {
  const cursorTime = currentTime.value
  const trackType = 'subtitle'

  const tracks_list = videoTrackRef.value.getTracks()
  let sameTypeTracks = tracks_list.filter(t => t.type === trackType)

  const maxOrder = tracks_list.reduce((max, track) => Math.max(max, track.order ?? 0), -1)
  let targetTrack = null
  let isNewTrack = false

  let maxIndex = 0
  const reg = new RegExp(`^(字幕)(\\d+)$`)
  sameTypeTracks.forEach(track => {
    const match = track.name.match(reg)
    if (match) {
      const num = parseInt(match[2], 10)
      if (num > maxIndex) maxIndex = num
    }
  })
  const nextIndex = maxIndex + 1

  if (sameTypeTracks.length === 0) {
    targetTrack = {
      id: `${trackType}-${Date.now()}`,
      type: trackType,
      name: `字幕${nextIndex}`,
      mainTrack: false,
      visible: true,
      locked: false,
      order: maxOrder + 1,
      clips: []
    }
    isNewTrack = true
  } else {
    for (const track of sameTypeTracks) {
      const isFreeTrack = track.clips.every(clip => clip.endTime <= cursorTime)
      if (isFreeTrack) {
        targetTrack = track
        break
      }
    }
    if (!targetTrack) {
      targetTrack = {
        id: `${trackType}-${Date.now()}`,
        type: trackType,
        name: `字幕${nextIndex}`,
        mainTrack: false,
        visible: true,
        locked: false,
        order: maxOrder + 1,
        clips: []
      }
      isNewTrack = true
    }
  }

  const newClip = {
    id: `clip-sub-${Date.now()}`,
    type: 'subtitle',
    name: ' 字幕 ',
    startTime: cursorTime,
    endTime: cursorTime + 5,
    source: '',
    sourceStartTime: 0,
    sourceEndTime: 5,
    originalDuration: 5,
    trimStart: 0,
    trimEnd: 5,
    transform: {
      x: 783/2,
      y: 450-30,
      scale: 1,
      rotate: 0
    },
    text: '测试字幕',
    style: {
      fontSize: 18,
      fill: '#ffffff',
      stroke: '#000000',
      strokeWidth: 3
    },
    thumbnails: [],
    waveformData: []
  }

  if (isNewTrack) {
    targetTrack.clips.push(newClip)
    videoTrackRef.value.addTrack(targetTrack)
  } else {
    videoTrackRef.value.addClip(targetTrack.id, newClip)
  }

  await nextTick()
  handleTrackSort()
  syncAllTracks()
  onClipSelect(newClip)
}
</script>

<style scoped>
.editor-wrap {
  height: 100vh;
  background: #14161d;
  color: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.editor-header {
  display: flex;
  justify-content: space-between;
  padding: 8px 16px;
  background: #1f212c;
}
.btn {
  padding: 6px 12px;
  background: #333647;
  border: none;
  color: #fff;
  border-radius: 4px;
  margin: 0 4px;
  cursor: pointer;
}
.btn.primary {
  background: #525aff;
}
.editor-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}
/* 左侧资源面板 */
.resource-sidebar {
  width: 350px;
  background: #1f212c;
  display: flex;
  flex-direction: column;
}
.tab-group {
  display: flex;
  border-bottom: 1px solid #333647;
}
.tab-item {
  padding: 10px 12px;
  font-size: 13px;
  color: #999;
  cursor: pointer;
}
.tab-item.active {
  color: #fff;
  border-bottom: 2px solid #525aff;
}
.resource-content {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
}
.import-btn {
  border: 1px dashed #555;
  text-align: center;
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 10px;
}
.material-item {
  display: inline-block;
  width: 85px;
  margin: 4px;
  position: relative;
  cursor: pointer;
  overflow: hidden;
}
/* 操作按钮容器 默认透明隐藏 */
.thumb-action {
  position: absolute;
  right: 0px;
  bottom: 20px;
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

/* hover素材显示按钮 */
.material-item:hover .thumb-action,
.sticker-item:hover .thumb-action {
  opacity: 1;
}

.thumb-action span {
  width: 15px;
  height: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  user-select: none;
}
.btn-add {
  background: #409eff;
}
.btn-del {
  background: #f56c6c;
}
.thumb-action span:hover {
  opacity: 0.85;
}
.material-item .thumb {
  width: 85px;
  height: 50px;
  background: #333;
  border-radius: 4px;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  background-color: #222;
}

.material-item .audio-thumb {
  background: #2a2d3b;
}

.material-item .name {
  font-size: 12px;
  color: #aaa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ========== 贴纸分类与网格样式 ========== */
.sticker-category-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.cat-tab {
  padding: 4px 10px;
  background: #2a2d3b;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  color: #ccc;
}
.cat-tab.active {
  background: #525aff;
  color: #fff;
}
.sticker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
}
.sticker-item {
  position: relative;
  height: 80px;
  background: #2a2d3b;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
}
.sticker-thumb {
  width: 100%;
  height: 100%;
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;
}
/* 滤镜item样式 */
.filter-thumb {
  display:flex;
  align-items:center;
  justify-content:center;
}
.filter-name-text{
  font-size:13px;
  color:#eee;
  text-align:center;
}

/* ======= 修改预览区域布局 ======= */
.preview-container {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.preview-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
}
.preview-property-wrap {
  width: 320px;
  background: #1f212c;
  overflow-y: auto;
  padding: 12px;
}

.panel-title {
  font-size: 16px;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #333647;
}
.prop-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.prop-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.prop-row label {
  font-size: 13px;
  color: #ccc;
}
.prop-row input,
.prop-row textarea {
  background: #2a2d3b;
  border: 1px solid #444;
  color: #fff;
  padding: 6px;
  border-radius: 4px;
}
/* 底部时间轴 */
.timeline-wrapper {
  height: 360px;
  border-top: 1px solid #333647;
}
/* =========导出弹窗样式【修复居中】========= */
.export-mask{
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0,0,0,0.65);
  display:flex;
  align-items:center;
  justify-content:center;
  z-index: 9999;
  overflow-y: auto; /* 屏幕小的时候弹窗可以滚动 */
  padding:12px 0;
}
:deep(.export-dialog) {
  width: 760px;
  max-width: calc(100vw - 24px);
  max-height: calc(100vh - 24px);
  background: #1f212c;
  border-radius:8px;
  color:#fff;
  overflow:hidden;
}
:deep(.dialog-header) {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:14px 18px;
  border-bottom:1px solid #333647;
}
:deep(.dialog-header .title) {
  font-size:16px;
}
:deep(.close-btn) {
  font-size:22px;
  cursor:pointer;
  color:#aaa;
}
:deep(.dialog-body) {
  display:flex;
  gap:24px;
  padding:20px;
  /* 内容区域溢出滚动，防止屏幕高度不够弹窗撑出去 */
  overflow-y:auto;
  max-height: calc(100vh - 140px);
}
:deep(.preview-col) {
  width:320px;
  flex-shrink:0;
}
:deep(.preview-label) {
  font-size:13px;
  color:#ccc;
  margin-bottom:8px;
}
:deep(.preview-box) {
  width:100%;
  height:180px;
  background:#2a2d3b;
  border-radius:4px;
  display:flex;
  align-items:center;
  justify-content:center;
  overflow:hidden;
}
:deep(.img-wrap img) {
  max-width:100%;
  max-height:180px;
  object-fit:contain;
}
:deep(.tip-text) {
  color:#999;
  font-size:13px;
  text-align:center;
  padding:12px;
}
:deep(.setting-col) {
  flex:1;
  display:flex;
  flex-direction:column;
  gap:16px;
}
:deep(.setting-row) {
  display:flex;
  flex-direction:column;
  gap:6px;
}
:deep(.setting-row label) {
  font-size:13px;
  color:#ccc;
}
:deep(.setting-row select) {
  height:34px;
  background:#2a2d3b;
  color:#fff;
  border:1px solid #444;
  border-radius:4px;
  padding:0 8px;
}
:deep(.dialog-footer) {
  padding:14px 18px;
  border-top:1px solid #333647;
  display:flex;
  justify-content:flex-end;
  gap:10px;
}
:deep(.dialog-footer .btn.cancel) {
  background:#333647;
}
</style>
