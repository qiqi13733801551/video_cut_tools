<template>
  <div class="property-panel">
    <div class="panel-title">属性面板</div>
    <div v-if="!selectedClip" class="empty-tip">请选中时间轴上片段</div>

    <!-- 视频/音频片段：多Tab选项卡 -->
    <div v-if="selectedClip">
      <div class="prop-tabs">
        <span
          v-for="tab in tabList"
          :key="tab.key"
          :class="['tab-item', {active:activeTab === tab.key}]"
          @click="activeTab = tab.key"
        >{{tab.label}}</span>
      </div>

      <!-- 素材信息 -->
      <div v-show="activeTab === 'info'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>名称</label>
            <span>{{localClip.name}}</span>
          </div>
          <div class="prop-row">
            <label>时长(s)</label>
            <input :value="formatTimeHmsms(localClip.endTime - localClip.startTime)" readonly />
          </div>
          <div class="prop-row">
            <label>源素材时长(s)</label>
            <input :value="formatTimeHmsms(localClip.originalDuration)" readonly />
          </div>
          <div class="prop-row">
            <label>入点(s)</label>
            <input :value="formatTimeHmsms(localClip.startTime)" readonly />
          </div>
          <div class="prop-row">
            <label>出点(s)</label>
            <input :value="formatTimeHmsms(localClip.endTime)" readonly />
          </div>
          <div class="prop-row" v-show="selectedClip.type === 'video'">
            <label>分辨率</label>
            <input 
              readonly
              :value="(localClip.naturalWidth ?? 0) + ' * ' + (localClip.naturalHeight ?? 0)"
            />
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'basic'&&selectedClip.type === 'video'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>播放倍速 {{localClip.playbackRate ?? 1.0}}x(此值在预览中不会生效,导出视频时会生效)</label>
            <input type="range" min="0.25" max="3" step="0.25" v-model.number="localClip.playbackRate" @input="emitUpdate('playbackRate')" />
          </div>
          <div class="prop-row">
            <label>位置 X</label>
            <input type="number" v-model.number="localClip.transform.x" @input="emitUpdate('transform.x')" />
          </div>
          <div class="prop-row">
            <label>位置 Y</label>
            <input type="number" v-model.number="localClip.transform.y" @input="emitUpdate('transform.y')" />
          </div>
          <div class="prop-row">
            <label>缩放 scale</label>
            <input type="number" step="0.01" v-model.number="localClip.transform.scale" @input="emitUpdate('transform.scale')" />
          </div>
          <div class="prop-row">
            <label>不透明度 {{(localClip.opacity??1).toFixed(2)}}</label>
            <input type="range" min="0" max="1" step="0.01" v-model.number="localClip.opacity" @input="emitUpdate('opacity')" />
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'basic'&&selectedClip.type === 'audio'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>音量 {{((localClip.volume ??1)*100).toFixed(0)}}%</label>
            <input type="range" min="0" max="1" step="0.01" v-model.number="localClip.volume" @input="emitUpdate('volume')" />
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'basic'&&selectedClip.type === 'subtitle'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>字幕文本</label>
            <textarea v-model="localClip.text" @input="emitUpdate('text')" rows="3"></textarea>
          </div>
          <div class="prop-row">
            <label>字号</label>
            <input type="number" v-model.number="localClip.style.fontSize" @input="emitUpdate('style.fontSize')" />
          </div>
          <div class="prop-row">
            <label>文字颜色</label>
            <input type="color" v-model="localClip.style.fill" @input="emitUpdate('style.fill')" />
          </div>
          <div class="prop-row">
            <label>描边颜色</label>
            <input type="color" v-model="localClip.style.stroke" @input="emitUpdate('style.stroke')" />
          </div>
          <div class="prop-row">
            <label>描边宽度</label>
            <input type="number" v-model.number="localClip.style.strokeWidth" @input="emitUpdate('style.strokeWidth')" />
          </div>
          <div class="prop-row">
            <label>X 位置</label>
            <input type="number" v-model.number="localClip.transform.x" @input="emitUpdate('transform.x')" />
          </div>
          <div class="prop-row">
            <label>Y 位置</label>
            <input type="number" v-model.number="localClip.transform.y" @input="emitUpdate('transform.y')" />
          </div>
          <div class="prop-row">
            <label>缩放 scale</label>
            <input type="number" step="0.01" v-model.number="localClip.transform.scale" @input="emitUpdate('transform.scale')" />
          </div>
          <div class="prop-row">
            <label>旋转 {{(localClip.transform.rotate ?? 0).toFixed(0)}}°</label>
            <input type="number" step="1" v-model.number="localClip.transform.rotate" @input="emitUpdate('transform.rotate')" />
          </div>

        </div>
      </div>

      <div v-if="activeTab === 'basic'&&selectedClip.type === 'sticker'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>X 位置</label>
            <input type="number" v-model.number="localClip.transform.x" @input="emitUpdate('transform.x')" />
          </div>
          <div class="prop-row">
            <label>Y 位置</label>
            <input type="number" v-model.number="localClip.transform.y" @input="emitUpdate('transform.y')" />
          </div>
          <div class="prop-row">
            <label>缩放 scale</label>
            <input type="number" step="0.01" v-model.number="localClip.transform.scale" @input="emitUpdate('transform.scale')" />
          </div>
          <div class="prop-row">
            <label>旋转 rotate</label>
            <input type="number" step="1" v-model.number="localClip.rotate" @input="emitUpdate('rotate')" />
          </div>
          <div class="prop-row">
            <label>不透明度 {{localClip.opacity.toFixed(2)}}</label>
            <input type="range" min="0" max="1" step="0.01" v-model.number="localClip.opacity" @input="emitUpdate('opacity')" />
          </div>

        </div>
      </div>

      <div v-if="activeTab === 'basic'&&selectedClip.type === 'filter'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>滤镜强度：{{ localClip.intensity.toFixed(2) }}</label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              v-model.number="localClip.intensity"
              @input="emitUpdate('intensity')"
            />
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'basic'&&selectedClip.type === 'effect'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>特效强度：{{ localClip.intensity.toFixed(2) }}</label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              v-model.number="localClip.intensity"
              @input="emitUpdate('intensity')"
            />
          </div>
        </div>
      </div>


      <!-- 音频：音量 -->
      <div v-show="activeTab === 'audio'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>音量 {{((localClip.volume ??1)*100).toFixed(0)}}%</label>
            <input type="range" min="0" max="1" step="0.01" v-model.number="localClip.volume" @input="emitUpdate('volume')" />
          </div>
        </div>
      </div>

      <!-- 调色选项卡（占位，后续可扩展调色shader参数） -->
            <!-- 调色选项卡 -->
      <div v-show="activeTab === 'color'" class="tab-content">
        <div class="prop-group">
          <div class="prop-row">
            <label>亮度 {{(localClip.brightness ?? 1.0).toFixed(2)}}</label>
            <input type="range" min="0" max="2" step="0.01" v-model.number="localClip.brightness" @input="emitUpdate('brightness')" />
          </div>
          <div class="prop-row">
            <label>对比度 {{(localClip.contrast ?? 1.0).toFixed(2)}}</label>
            <input type="range" min="0" max="2" step="0.01" v-model.number="localClip.contrast" @input="emitUpdate('contrast')" />
          </div>
          <div class="prop-row">
            <label>饱和度 {{(localClip.saturation ?? 1.0).toFixed(2)}}</label>
            <input type="range" min="0" max="2" step="0.01" v-model.number="localClip.saturation" @input="emitUpdate('saturation')" />
          </div>
          <div class="prop-row">
            <label>色温 {{(localClip.temp ?? 0).toFixed(0)}}</label>
            <input type="range" min="-100" max="100" step="1" v-model.number="localClip.temp" @input="emitUpdate('temp')" />
          </div>
          <div class="prop-row">
            <label>色调 {{(localClip.tint ?? 0).toFixed(0)}}</label>
            <input type="range" min="-100" max="100" step="1" v-model.number="localClip.tint" @input="emitUpdate('tint')" />
          </div>
          <div class="prop-row">
            <label>暗角比例 {{(localClip.vignette ?? 0).toFixed(2)}}</label>
            <input type="range" min="0" max="1" step="0.01" v-model.number="localClip.vignette" @input="emitUpdate('vignette')" />
          </div>

          <div style="text-align:left;margin-bottom:8px;">
            <button class="reset-color-btn" @click="resetColorAdjust()">重置调色</button>
          </div>

        </div>
      </div>

    </div>

    <!-- 音频片段（非视频，单独简单面板） -->
    <div v-if="selectedClip && selectedClip.type === 'audio' && !(['video','audio'].includes(selectedClip.type))" class="prop-group">
      <div class="prop-row">
        <label>音频名称</label>
        <input v-model="localClip.name" />
      </div>
    </div>

  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
const props = defineProps<{
  selectedClip: any
}>()
const emit = defineEmits<{
  'update:clip': [clip: any, changedKey?: string]
}>()

// 根据选中片段类型动态计算tab列表
const tabList = computed(() => {
  const clip = props.selectedClip
  if (!clip) return []
  if (clip.type === 'video') {
    return [
      { key:'info', label:'素材信息'},
      { key:'basic', label:'基础'},
      { key:'audio', label:'音频'},
      { key:'color', label:'调色'}
    ]
  } else if (clip.type === 'audio') {
    return [
      { key:'info', label:'素材信息'},
      { key:'basic', label:'基础'}
    ]
  } else if (clip.type === 'subtitle') {
    return [
      { key:'info', label:'素材信息'},
      { key:'basic', label:'基础'}
    ]
  } else if (clip.type === 'sticker') {
    return [
      { key:'info', label:'素材信息'},
      { key:'basic', label:'基础'}
    ]
  } else if (clip.type === 'filter') {
    return [
      { key:'info', label:'素材信息'},
      { key:'basic', label:'基础'}
    ]
  }else if (clip.type === 'effect') {
    return [
      { key:'info', label:'素材信息'},
      { key:'basic', label:'基础'}
    ]
  }else if (clip.type === 'transition') {
    return [
      { key:'info', label:'素材信息'}
    ]
  }
  return []
})

const activeTab = ref('basic')

// 监听选中clip变化，做tab容错：如果当前activeTab不在新tabList，自动切到第一项
watch(() => props.selectedClip, () => {
  const tabs = tabList.value
  if(!tabs || tabs.length ===0) return
  const exist = tabs.some(t => t.key === activeTab.value)
  if(!exist){
    activeTab.value = tabs[0].key
  }
},{flush:'post'})

/**
 * 将总秒数 → HH:mm:ss:ms  00:01:11:00
 * @param totalSeconds 总秒数 number
 */
function formatTimeHmsms(totalSeconds: number): string {
  if (isNaN(totalSeconds) || totalSeconds < 0) totalSeconds = 0;
  const hours = Math.floor(totalSeconds / 3600);
  const remain1 = totalSeconds % 3600;
  const minutes = Math.floor(remain1 / 60);
  const seconds = Math.floor(remain1 % 60);
  // 取小数部分 *100 得到两位毫秒
  const ms = Math.floor((totalSeconds - Math.floor(totalSeconds)) * 100);
  const pad2 = (n: number) => String(n).padStart(2, '0');
  return `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}:${pad2(ms)}`;
}
// 本地副本，防止直接修改父源数据，增加默认兜底值
const localClip = computed(() => {
  if (!props.selectedClip) return null
  const c = JSON.parse(JSON.stringify(props.selectedClip))
  // 兜底默认值
  c.playbackRate ??= 1.0
  c.volume ??= 1.0
  c.opacity ??= 1.0
  c.width ??= c.naturalWidth ?? 720
  c.height ??= c.naturalHeight ?? 405
  if(!c.transform) c.transform = {x:0,y:0,scale:1}
  c.transform.rotate ??= 0
  // =====新增调色参数兜底=====
  c.brightness ??= 1.0
  c.contrast ??= 1.0
  c.saturation ??= 1.0
  c.temp ??= 0
  c.tint ??= 0
  c.vignette ??= 0
  return c
})
/** 重置全部调色参数为默认值，并向上emit更新 */
function resetColorAdjust() {
  if (!localClip.value) return
  // 赋值默认调色值
  localClip.value.brightness = 1.0
  localClip.value.contrast = 1.0
  localClip.value.saturation = 1.0
  localClip.value.temp = 0
  localClip.value.tint = 0
  localClip.value.vignette = 0
  // 通知父组件更新clip数据
  emit('update:clip', localClip.value, 'resetColor')
}
/**
 * @param changedKey 修改的属性名，例如 "playbackRate" / "opacity" / "transform.x"
 */
function emitUpdate(changedKey?: string) {
  if (!localClip.value) return
  emit('update:clip', localClip.value, changedKey)
}
</script>
<style scoped>
.property-panel {
  height: 100%;
  overflow-y: auto;
}
.panel-title {
  font-size: 16px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #333647;
}
.empty-tip {
  color: #888;
  font-size:13px;
}
/* tab选项卡 */
.prop-tabs{
  display:flex;
  gap:4px;
  margin-bottom:14px;
  border-bottom:1px solid #333647;
}
.tab-item{
  padding:6px 10px;
  font-size:13px;
  cursor:pointer;
  color:#999;
  border-bottom:2px solid transparent;
}
.tab-item.active{
  color:#fff;
  border-bottom-color:#525aff;
}
.tab-content{
  margin-bottom:10px;
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
textarea {
  resize: vertical;
}
.tip{
  color:#888;
  font-size:12px;
}
.reset-color-btn{
  background:#333647;
  color:#fff;
  border:1px solid #444;
  border-radius:4px;
  padding:3px 8px;
  font-size:12px;
  cursor:pointer;
}
.reset-color-btn:hover{
  background:#44485c;
}
</style>
