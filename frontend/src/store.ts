import { defineStore } from 'pinia'
import { ref } from 'vue'
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}
export async function api(path: string, options: RequestInit = {}) {
  let response: Response
  try {
    response = await fetch('/api' + path, { ...options, signal: options.signal ?? AbortSignal.timeout(30000), headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } })
  } catch (error: any) {
    throw new ApiError(error.name === 'TimeoutError' ? '请求超时，请稍后重试' : '连接中断，请检查网络后重试', 0)
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(typeof data?.detail === 'string' ? data.detail : '请求未完成，请检查输入后重试', response.status)
  return data
}
export const useWardrobe = defineStore('wardrobe', () => {
  const user = ref<any>(null), items = ref<any[]>([]), recommendations = ref<any[]>([]), jobs = ref<any[]>([]), conversations = ref<any[]>([])
  let inFlight: Promise<void> | null = null
  let generation = 0
  function reset() {
    generation++
    user.value = null; items.value = []; recommendations.value = []; jobs.value = []; conversations.value = []
    inFlight = null
  }
  function refresh(): Promise<void> {
    if (inFlight) return inFlight
    const started = generation
    const request = Promise.all([api('/me'), api('/items'), api('/recommendations'), api('/jobs'), api('/conversations')])
      .then(values => {
        if (started !== generation) return
        ;[user.value, items.value, recommendations.value, jobs.value, conversations.value] = values
      })
      .catch(error => { if (started === generation && error.status === 401) reset(); throw error })
      .finally(() => { if (inFlight === request) inFlight = null })
    inFlight = request
    return request
  }
  return { user, items, recommendations, jobs, conversations, refresh, reset }
})
