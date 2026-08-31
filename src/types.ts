// types.ts
export interface MediaClip {
  id: string
  type: 'video' | 'audio'
  name: string
  startTime: number
  endTime: number
  source: string
  sourceStartTime: number
  sourceEndTime: number
  originalDuration:number
  trimStart: number
  trimEnd: number
  playbackRate:number
  thumbnails?: string[]
  waveform?: number[]
}