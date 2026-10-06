/**
 * OH-Q.2 首批单测：表单校验工具（纯函数，jsdom 无关）
 */
import { describe, it, expect } from 'vitest'
import {
  trimSpaces,
  validatePhone,
  validateEmail,
  validateIPv4Address,
  validatePassword,
  validateStrongPassword,
  validateAccount,
  getPasswordStrength,
  PasswordStrength,
} from '@/utils/form/validator'

describe('trimSpaces', () => {
  it('去除首尾空白', () => {
    expect(trimSpaces('  abc  ')).toBe('abc')
    expect(trimSpaces('a b c')).toBe('a b c')
  })
})

describe('validatePhone', () => {
  it('合法手机号通过', () => {
    expect(validatePhone('13800138000')).toBe(true)
    expect(validatePhone('19912345678')).toBe(true)
  })
  it('非法手机号拒绝', () => {
    expect(validatePhone('12345678901')).toBe(false) // 非 1[3-9]
    expect(validatePhone('1380013800')).toBe(false)  // 10 位
    expect(validatePhone('1380013800a')).toBe(false)
  })
})

describe('validateEmail', () => {
  it('合法邮箱通过', () => {
    expect(validateEmail('user@example.com')).toBe(true)
    expect(validateEmail('a.b+c@sub.domain.org')).toBe(true)
  })
  it('非法邮箱拒绝', () => {
    expect(validateEmail('plainaddress')).toBe(false)
    expect(validateEmail('@b.com')).toBe(false)
  })
})

describe('validateIPv4Address', () => {
  it('合法 IPv4 通过', () => {
    expect(validateIPv4Address('192.168.1.1')).toBe(true)
    expect(validateIPv4Address('0.0.0.0')).toBe(true)
    expect(validateIPv4Address('255.255.255.255')).toBe(true)
  })
  it('非法 IPv4 拒绝', () => {
    expect(validateIPv4Address('256.1.1.1')).toBe(false)
    expect(validateIPv4Address('1.2.3')).toBe(false)
    expect(validateIPv4Address('abc')).toBe(false)
    expect(validateIPv4Address('1.2.3.4.5')).toBe(false)
  })
})

describe('validatePassword / strength', () => {
  it('基础密码规则', () => {
    expect(validatePassword('abc12345')).toBe(true)
    expect(validatePassword('123')).toBe(false) // 太短
  })
  it('强密码要求含大小写数字符号', () => {
    expect(validateStrongPassword('Abcdef1!')).toBe(true)
    expect(validateStrongPassword('abcdef1!')).toBe(false) // 无大写
    expect(validateStrongPassword('ABCDEF1!')).toBe(false) // 无小写
    expect(validateStrongPassword('Abcdefg!')).toBe(false) // 无数字
  })
  it('密码强度分档', () => {
    expect(getPasswordStrength('aaaaaa')).toBe(PasswordStrength.WEAK)
    expect(getPasswordStrength('Abcdef1!xyz')).toBe(PasswordStrength.STRONG)
  })
})

describe('validateAccount', () => {
  it('字母开头 4-20 位字母数字下划线', () => {
    expect(validateAccount('user_01')).toBe(true)
    expect(validateAccount('01user')).toBe(false) // 数字开头
    expect(validateAccount('ab')).toBe(false)     // 太短
  })
})
