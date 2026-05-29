import request from '@/utils/http'

/**
 * 获取验证码
 * GET /api/v1/auth/captcha
 */
export async function fetchCaptcha(): Promise<Api.Auth.CaptchaResponse> {
  const res = await request.get<any>({
    url: '/api/v1/auth/captcha',
    showErrorMessage: false
  })
  return res as Api.Auth.CaptchaResponse
}

/**
 * 登录
 * POST /api/v1/auth/login
 */
export async function fetchLogin(params: Api.Auth.LoginParams): Promise<Api.Auth.LoginResponse> {
  const res = await request.post<any>({
    url: '/api/v1/auth/login',
    data: params,
    showErrorMessage: false
  })

  return res as Api.Auth.LoginResponse
}

/**
 * 获取当前用户信息
 * GET /api/v1/auth/me
 */
export function fetchGetUserInfo() {
  return request.get<Api.Auth.UserInfo>({
    url: '/api/v1/auth/me',
    showErrorMessage: false
  })
}

/**
 * 更新用户信息
 * PUT /api/v1/users/{id}
 */
export function fetchUpdateUserInfo(
  data: Partial<Api.Auth.UserInfo> & { id: number | string; password?: string }
) {
  const { id, ...rest } = data
  return request.put<void>({
    url: `/api/v1/users/${id}`,
    data: rest,
    showSuccessMessage: false
  })
}

/**
 * 刷新访问令牌
 * POST /api/v1/auth/refresh
 */
export async function fetchRefreshToken(refreshToken: string): Promise<{ access_token: string; expires_in: number }> {
  const res = await request.post<any>({
    url: '/api/v1/auth/refresh',
    data: { refresh_token: refreshToken },
    showErrorMessage: false
  })

  return {
    access_token: res.access_token,
    expires_in: res.expires_in
  }
}
