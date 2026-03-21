// tests/helpers/test-data.ts

/**
 * 用户数据接口
 */
export interface UserData {
  username: string;
  password: string;
  email: string;
  full_name: string;
  role_id: number;
}

/**
 * 用户数据覆盖接口（允许部分覆盖）
 */
export type UserDataOverrides = Partial<UserData>;

/**
 * 生成测试用户数据
 *
 * @param overrides - 可选的用户数据覆盖项，用于自定义特定字段
 * @returns 包含完整用户数据的对象
 *
 * @example
 * ```typescript
 * // 使用默认值
 * const userData = generateUserData();
 *
 * // 自定义部分字段
 * const customUser = generateUserData({
 *   username: 'johndoe',
 *   full_name: 'John Doe'
 * });
 * ```
 */
export const generateUserData = (overrides: UserDataOverrides = {}): UserData => ({
  username: `testuser_${Date.now()}`,
  password: 'Test123456!',
  email: `test${Date.now()}@example.com`,
  full_name: '测试用户',
  role_id: 2, // 普通用户角色
  ...overrides
});


/**
 * 生成有效的密码
 *
 * 生成符合安全要求的随机密码，确保包含大小写字母、数字和特殊字符
 *
 * @returns 12位长度的随机密码字符串
 *
 * @example
 * ```typescript
 * const password = generatePassword();
 * // 示例输出: "Aa1!xY7@kL2$m"
 * ```
 */
export const generatePassword = (): string => {
  const length = 12;
  const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
  let password = '';

  // 确保包含大小写字母、数字和特殊字符
  password += 'A'; // 大写
  password += 'a'; // 小写
  password += '1'; // 数字
  password += '!'; // 特殊字符

  for (let i = 0; i < length - 4; i++) {
    password += charset[Math.floor(Math.random() * charset.length)];
  }

  return password;
};


/**
 * 用户凭据接口
 */
export interface UserCredentials {
  username: string;
  password: string;
}

/**
 * 测试凭据集合接口
 */
export interface TestCredentials {
  admin: UserCredentials;
  regularUser: UserCredentials;
}

/**
 * 获取测试用户凭据
 *
 * 返回预定义的测试用户凭据，包括管理员和普通用户
 *
 * @returns 包含管理员和普通用户凭据的对象
 *
 * @example
 * ```typescript
 * const creds = getTestCredentials();
 * console.log(creds.admin); // { username: 'admin', password: 'admin123' }
 * console.log(creds.regularUser); // { username: 'testuser', password: 'Test123456!' }
 * ```
 */
export const getTestCredentials = (): TestCredentials => ({
  admin: {
    username: 'admin',
    password: 'admin123'
  },
  regularUser: {
    username: 'testuser',
    password: 'Test123456!'
  }
});
