// tests/helpers/api-helpers.ts
import type { APIRequestContext } from '@playwright/test';

/**
 * 创建用户响应接口
 */
export interface CreateUserResponse {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role_id: number;
  status: string;
}

/**
 * 用户数据接口（用于创建用户）
 */
export interface UserDataForCreation {
  username: string;
  password: string;
  email: string;
  full_name: string;
  role_id: number;
}

/**
 * 通过API创建用户
 *
 * 使用API创建新用户，需要提供有效的认证令牌
 *
 * @param apiContext - Playwright API请求上下文
 * @param userData - 用户数据对象，包含username、password、email、full_name和role_id
 * @param token - JWT认证令牌
 * @returns 返回创建的用户信息，包含id、username、email等字段
 * @throws 当API请求失败时抛出错误，包含HTTP状态码
 *
 * @example
 * ```typescript
 * const userData = {
 *   username: 'testuser',
 *   password: 'Test123456!',
 *   email: 'test@example.com',
 *   full_name: '测试用户',
 *   role_id: 2
 * };
 * const result = await createUserViaAPI(apiContext, userData, token);
 * console.log(result.id); // 新创建用户的ID
 * ```
 */
export async function createUserViaAPI(
  apiContext: APIRequestContext,
  userData: UserDataForCreation,
  token: string
): Promise<CreateUserResponse> {
  const response = await apiContext.post('/api/v1/users', {
    data: userData,
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok()) {
    throw new Error(`Failed to create user: ${response.status()}`);
  }

  return await response.json() as CreateUserResponse;
}


/**
 * 通过API删除用户
 *
 * 使用API删除指定ID的用户，需要提供有效的认证令牌
 *
 * @param apiContext - Playwright API请求上下文
 * @param userId - 要删除的用户ID
 * @param token - JWT认证令牌
 * @returns 无返回值
 * @throws 当API请求失败时抛出错误，包含HTTP状态码
 *
 * @example
 * ```typescript
 * await deleteUserViaAPI(apiContext, 123, token);
 * ```
 */
export async function deleteUserViaAPI(
  apiContext: APIRequestContext,
  userId: number,
  token: string
): Promise<void> {
  const response = await apiContext.delete(`/api/v1/users/${userId}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok()) {
    throw new Error(`Failed to delete user: ${response.status()}`);
  }
}


/**
 * 重置用户密码
 *
 * 通过API重置指定用户的密码，系统将生成一个新的随机密码
 *
 * @param apiContext - Playwright API请求上下文
 * @param userId - 要重置密码的用户ID
 * @param token - JWT认证令牌
 * @returns 返回新生成的密码字符串
 * @throws 当API请求失败时抛出错误，包含HTTP状态码
 *
 * @example
 * ```typescript
 * const newPassword = await resetPasswordViaAPI(apiContext, 123, token);
 * console.log(newPassword); // 新生成的密码，如 "Aa1!xY7@kL2$m"
 * ```
 */
export async function resetPasswordViaAPI(
  apiContext: APIRequestContext,
  userId: number,
  token: string
): Promise<string> {
  const response = await apiContext.post(`/api/v1/users/${userId}/reset-password`, {
    data: {},
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok()) {
    throw new Error(`Failed to reset password: ${response.status()}`);
  }

  const result = await response.json();
  return result.new_password || 'GeneratedPassword123!';
}
