// tests/setup/db-setup.ts
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

const MIGRATION_FILE = path.resolve(
  __dirname,
  '../../../backend/migrations/postgresql/001_system_management.sql'
);

/**
 * 初始化测试数据库
 */
export function setupDatabase(): void {
  const dbUrl = process.env.TEST_DATABASE_URL;

  if (!dbUrl) {
    throw new Error('TEST_DATABASE_URL environment variable not set');
  }

  console.log('Setting up test database...');

  // 检查迁移文件是否存在
  if (!fs.existsSync(MIGRATION_FILE)) {
    throw new Error(`Migration file not found: ${MIGRATION_FILE}`);
  }

  // 执行迁移文件
  try {
    execSync(`psql "${dbUrl}" -f "${MIGRATION_FILE}"`, {
      stdio: 'inherit'
    });
    console.log('✅ Database schema initialized');
  } catch (error) {
    console.error('❌ Failed to initialize database:', error);
    throw error;
  }
}

/**
 * 清空测试数据库
 */
export function resetDatabase(): void {
  const dbUrl = process.env.TEST_DATABASE_URL;

  if (!dbUrl) {
    throw new Error('TEST_DATABASE_URL environment variable not set');
  }

  console.log('Resetting test database...');

  try {
    execSync(`psql "${dbUrl}" -c "DROP SCHEMA public CASCADE"`, {
      stdio: 'inherit'
    });
    execSync(`psql "${dbUrl}" -c "CREATE SCHEMA public"`, {
      stdio: 'inherit'
    });
    console.log('✅ Database reset complete');
  } catch (error) {
    console.error('❌ Failed to reset database:', error);
    throw error;
  }
}

/**
 * 加载测试种子数据
 */
export function seedDatabase(): void {
  const dbUrl = process.env.TEST_DATABASE_URL;

  if (!dbUrl) {
    throw new Error('TEST_DATABASE_URL environment variable not set');
  }

  const seedFile = path.resolve(__dirname, 'test-seed.sql');

  if (!fs.existsSync(seedFile)) {
    throw new Error(`Seed file not found: ${seedFile}`);
  }

  console.log('Seeding test database...');

  try {
    execSync(`psql "${dbUrl}" -f "${seedFile}"`, {
      stdio: 'inherit'
    });
    console.log('✅ Test data seeded successfully');
  } catch (error) {
    console.error('❌ Failed to seed database:', error);
    throw error;
  }
}
