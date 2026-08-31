<template>
  <div style="width:100%;height:100vh;padding:16px;box-sizing:border-box;">
    <div style="margin-bottom:12px;">
      <!-- 本地文件选择 -->
      <input
        type="file"
        accept="video/*"
        @change="handleSelectVideo"
      />
    </div>

    <!-- 剪辑轨道核心组件 -->
    <VideoTrack
      ref="videoTrackRef"
      :enable-main-track-mode="true"
      :track-types="trackTypes"
      :operation-buttons="operationButtons"
      :enable-snap="true"
      :scale-config-buttons="['snap']"
      :thumbnail-height="60"
      :enable-cross-track-drag="true"
      style="height: 500px;border:1px solid #ccc;"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { VideoTrack,extractVideoThumbnails } from 'vue-clip-track'
import type { MediaClip } from './types'

const videoTrackRef = ref<InstanceType<typeof VideoTrack>>()

// 轨道类型配置
const trackTypes = ref({
  video: { max: 5 },
  audio: { max: 3 }
})

const operationButtons = [
  'reset',   // 重置
  'undo',    // 撤销
  'redo',    // 重做
  'split',   // 分割素材
  'delete'   // 删除
]

/**
 * 上传视频入口
 */
async function handleSelectVideo(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const videoUrl = URL.createObjectURL(file)
  const meta = await getVideoMetadata(videoUrl)

  // 第二个参数：生成多少张缩略图
  const thumbnails_list = await extractVideoThumbnails(videoUrl, Math.floor(Number(meta.duration)))
  console.log('生成缩略图数组：', thumbnails_list)

  console.log('meta.duration', Math.floor(Number(meta.duration)))


  const clip: MediaClip = {
    id: `clip-${Date.now()}`,
    type: 'video',
    name: file.name,
    startTime: 0,
    endTime: meta.duration,
    source: videoUrl,
    sourceStartTime: 0,
    sourceEndTime: meta.duration,
    originalDuration:meta.duration,
    trimStart: 0,
    trimEnd: meta.duration,
    thumbnails:thumbnails_list.thumbnails
  }

console.log('clip',clip);

  // 添加轨道
  videoTrackRef.value.addTrack({
    id: 'video-1',
    type: 'video',
    name: '视频轨道 1',
    visible: true, // ✅ 控制小眼睛显示状态，true=开启可见
    locked: false, // 控制锁图标（锁定轨道）
    clips: [clip]
  })

}

/**
 * 获取视频元信息
 */
function getVideoMetadata(src: string): Promise<{ duration: number }> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video')
    video.src = src
    video.preload = 'metadata'
    video.onloadedmetadata = () => {
      resolve({ duration: video.duration })
    }
    video.onerror = reject
  })
}
</script>