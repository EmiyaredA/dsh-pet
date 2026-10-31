#!/usr/bin/env node
import { cpSync, existsSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

export function animationNames(config) {
  const a = config.animations;
  const names = [...a.idle, ...a.turn, ...a.drag, ...a.clicks,
    ...a.moves.actions.map(x => x.name), ...a.categories.flatMap(x => x.actions),
    ...Object.values(a.events).flatMap(slots => slots.flat())];
  for (const name of names) {
    if (typeof name !== 'string' || !name || /[\\/\x00]/.test(name) || name === '.' || name === '..') {
      throw new Error('非法动画名');
    }
  }
  return new Set(names);
}

export function installPack({ packRoot, dshHome, update = false }) {
  const source = join(packRoot, 'pet');
  const target = join(resolve(dshHome), 'dsh-pet', 'pet');
  const configPath = join(target, 'kurisu-config.json');
  const animationPath = join(target, 'kurisu-animation');
  const config = JSON.parse(readFileSync(join(source, 'kurisu-config.json'), 'utf8'));
  for (const name of animationNames(config)) {
    if (!existsSync(join(source, 'kurisu-animation', `${name}.webm`))) throw new Error(`缺少动画：${name}`);
  }
  const exists = existsSync(configPath) || existsSync(animationPath);
  if (exists && !update) throw new Error('目标宠物包已存在；需要更新时显式使用 --update。');
  if (existsSync(configPath)) {
    const old = JSON.parse(readFileSync(configPath, 'utf8'));
    if (Array.isArray(old.pets) && old.pets.length) {
      // `facing` is not a persistent host Pet field today. Retain an existing
      // raw compatibility value without inventing one; the live renderer keeps
      // its actual session-facing state during animation hot updates.
      const fields = ['id', 'name', 'size', 'position', 'display', 'whisperPrompt', 'facing'];
      config.pets = old.pets.map(pet => ({ ...config.pets[0],
        ...Object.fromEntries(fields.filter(key => key in pet).map(key => [key, pet[key]])) }));
    }
    // These supported species-level display preferences can be customized in
    // this file. Behavior switches and animation pools come from the new pack.
    for (const key of ['font', 'confineToScreen']) {
      if (Object.hasOwn(old, key)) config[key] = old[key];
    }
  }
  mkdirSync(target, { recursive: true });
  const stage = join(target, `.kurisu-stage-${randomUUID()}`);
  const backup = exists ? join(target, 'backups', `kurisu-${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0,8)}`) : null;
  let movedConfig = false, movedAnimation = false, installedConfig = false, installedAnimation = false;
  try {
    mkdirSync(stage);
    cpSync(join(source, 'kurisu-animation'), join(stage, 'kurisu-animation'), { recursive: true });
    writeFileSync(join(stage, 'kurisu-config.json'), JSON.stringify(config, null, 2) + '\n');
    if (backup) {
      mkdirSync(backup, { recursive: true });
      if (existsSync(configPath)) { renameSync(configPath, join(backup, 'kurisu-config.json')); movedConfig = true; }
      if (existsSync(animationPath)) { renameSync(animationPath, join(backup, 'kurisu-animation')); movedAnimation = true; }
    }
    renameSync(join(stage, 'kurisu-animation'), animationPath); installedAnimation = true;
    renameSync(join(stage, 'kurisu-config.json'), configPath); installedConfig = true;
  } catch (error) {
    if (installedConfig) rmSync(configPath);
    if (installedAnimation) rmSync(animationPath, { recursive: true });
    if (movedConfig) renameSync(join(backup, 'kurisu-config.json'), configPath);
    if (movedAnimation) renameSync(join(backup, 'kurisu-animation'), animationPath);
    throw error;
  } finally {
    rmSync(stage, { recursive: true, force: true });
  }
  return { destination: target, backup, instances: config.pets.length };
}

if (process.argv[1] && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url))) {
  const args = process.argv.slice(2);
  const index = args.indexOf('--dsh-home');
  const known = args.filter((_, i) => i !== index && i !== index + 1);
  if (index < 0 || !args[index + 1] || known.some(x => x !== '--update')) {
    console.log('用法：node install.mjs --dsh-home <DSH 数据根目录> [--update]');
    process.exit(args.includes('--help') ? 0 : 2);
  }
  const result = installPack({ packRoot: dirname(fileURLToPath(import.meta.url)), dshHome: args[index + 1], update: args.includes('--update') });
  console.log(`红莉栖宠物包已安装到 ${result.destination}`);
  if (result.backup) console.log(`旧包备份：${result.backup}`);
  console.log('刷新 DSH 网页，或重载桌宠配置即可加载；肥鱼和全局设置保留。');
}
