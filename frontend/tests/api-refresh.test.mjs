import test from 'node:test';
import assert from 'node:assert/strict';

test('stalled API request times out without retry or clearing operation outcome', async()=>{
  const {request}=await import('../src/api.mjs?timeout-test');
  const original=globalThis.fetch;let calls=0;
  globalThis.fetch=(_url,{signal})=>new Promise((_resolve,reject)=>{
    calls++;signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});
  });
  try {
    await assert.rejects(request('state/',{timeoutMs:20}),error=>error.name==='TimeoutError'&&error.status===undefined);
    assert.equal(calls,1);
  } finally {globalThis.fetch=original;}
});

test('external navigation cancellation aborts pending fetch',async()=>{
  const {request}=await import('../src/api.mjs?abort-test');
  const original=globalThis.fetch;
  globalThis.fetch=(_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
  try {
    const controller=new AbortController();const pending=request('state/',{signal:controller.signal});
    controller.abort();await assert.rejects(pending,error=>error.name==='AbortError');
  } finally {globalThis.fetch=original;}
});

test('response body timeout is not swallowed as an empty successful response',async()=>{
  const {request}=await import('../src/api.mjs?body-timeout');
  const original=globalThis.fetch;
  globalThis.fetch=async(_url,{signal})=>({status:200,ok:true,json:()=>new Promise((_resolve,reject)=>
    signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}))});
  try {await assert.rejects(request('state/',{timeoutMs:20}),error=>error.name==='TimeoutError');}
  finally {globalThis.fetch=original;}
});

test('expired access refreshes once and retries concurrent requests', async () => {
  const { request } = await import('../src/api.mjs?refresh-test');
  const original = globalThis.fetch;
  const calls = [];
  let refreshed = false;
  globalThis.fetch = async (url, options) => {
    calls.push({url, options});
    if (url.endsWith('auth/csrf/')) return Response.json({csrfToken:'test-csrf'});
    if (url.endsWith('auth/refresh/')) {
      await new Promise(resolve => setTimeout(resolve, 10));
      refreshed = true;
      return Response.json({csrfToken:'test-csrf'});
    }
    return Response.json(refreshed ? {ok:true} : {detail:'expired'}, {status:refreshed ? 200 : 401});
  };
  try {
    const result = await Promise.all([request('state/'), request('admin/dashboard/')]);
    assert.equal(result.every(item => item.ok),true);
    assert.equal(calls.filter(call => call.url.endsWith('auth/refresh/')).length,1);
    assert.equal(calls.find(call => call.url.endsWith('auth/refresh/')).options.headers['X-CSRFToken'],'test-csrf');
  } finally { globalThis.fetch = original; }
});

test('invalid login does not silently refresh or retry', async () => {
  const { request } = await import('../src/api.mjs?login-test');
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({message:'Invalid'}, {status:401}); };
  try {
    await assert.rejects(request('auth/login/',{method:'POST'}), /Invalid/);
    assert.equal(calls,1);
  } finally { globalThis.fetch = original; }
});
