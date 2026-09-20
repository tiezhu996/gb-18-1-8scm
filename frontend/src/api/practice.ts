import request from './request'
import type {
  Question,
  PracticeResult,
  PracticeSession,
  QuotaReport,
  QuotaShortageDetail
} from '@/types'

export interface StartPracticeParams {
  mode: string
  subject_id: string
  knowledge_ids?: string[]
  question_count: number
  difficulty?: string
  // 按难度配额抽题：简单/中等/困难三档需求，三档之和必须等于总题数
  easy_count?: number
  medium_count?: number
  hard_count?: number
}

export interface StartPracticeResponse {
  session_id: string
  current_question: Question
  progress: { current: number; total: number; correct: number; accuracy: number }
  // 创建成功后按题号快照继续，携带各档实际抽中与补位结果
  quota_report?: QuotaReport
}

export const startPractice = (data: StartPracticeParams) => {
  return request.post<StartPracticeResponse>('/practice/start', data)
}

export const submitAnswer = (sessionId: string, questionId: string, userAnswer: any) => {
  return request.post<PracticeResult>('/practice/submit', {
    session_id: sessionId,
    question_id: questionId,
    user_answer: userAnswer
  })
}

export const navigateQuestion = (sessionId: string, direction: 'prev' | 'next') => {
  return request.get<Question>(`/practice/navigate/${sessionId}/${direction}`)
}

export const getSessionProgress = (sessionId: string) => {
  return request.get<{
    current: number
    total: number
    correct: number
    accuracy: number
    answers: Record<string, any>
  }>(`/practice/progress/${sessionId}`)
}

// 按题号快照恢复会话（刷新/二次进入时继续，不会重新抽题）
export const getPracticeSession = (sessionId: string) => {
  return request.get<{ session: PracticeSession; current_question: Question | null }>(
    `/practice/session/${sessionId}`
  )
}

// 后端整批拒绝时 detail 为结构化缺口报告，调用方据此展示每档需求/可用/缺口
export const isQuotaShortage = (error: any): error is { response: { data: { detail: QuotaShortageDetail } } } => {
  return error?.response?.status === 422 &&
    error?.response?.data?.detail?.code === 'QUOTA_SHORTAGE'
}

export const getQuotaShortage = (error: any): QuotaShortageDetail | null => {
  return isQuotaShortage(error) ? error.response.data.detail : null
}
