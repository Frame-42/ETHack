import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
test('server serves public artifacts and does not expose repository internals',async()=>{
  const child=spawn(process.execPath,['scripts/serve.mjs'],{cwd:new URL('..',import.meta.url),env:{...process.env,PORT:'4184'},stdio:['ignore','pipe','pipe']});
  try{
    await new Promise((resolve,reject)=>{child.stdout.once('data',resolve);child.once('error',reject);child.once('exit',()=>reject(new Error('Server exited before listening')));});
    for(const path of ['/','/src/app.mjs','/data/processed/companies.json','/docs/methodology.md'])assert.equal((await fetch('http://127.0.0.1:4184'+path)).status,200,path);
    for(const path of ['/.git/config','/data/cache/directory.json','/package.json','/%2e%2e/.git/config','/not-found'])assert.equal((await fetch('http://127.0.0.1:4184'+path)).status,404,path);
  }finally{child.kill();}
});
