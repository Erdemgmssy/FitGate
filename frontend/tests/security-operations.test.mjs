import test from "node:test";
import assert from "node:assert/strict";
import { operation, pendingOperation, clearPendingOperation } from "../src/api.mjs";
test('Pending operations are isolated between admin and staff accounts',async()=>{
  const previousFetch=globalThis.fetch,previousStorage=globalThis.sessionStorage;
  const map=new Map();globalThis.sessionStorage={getItem:key=>map.get(key)||null,setItem:(key,value)=>map.set(key,value),removeItem:key=>map.delete(key)};
  globalThis.fetch=async()=>new Response(JSON.stringify({message:'Temporary failure'}),{status:503});
  try{await assert.rejects(operation('collect',{amount:'10'},1));await assert.rejects(operation('collect',{amount:'20'},2));const first=pendingOperation(1),second=pendingOperation(2);assert.notEqual(first.key,second.key);await assert.rejects(operation('collect',{amount:'10'},1));assert.equal(pendingOperation(1).key,first.key);clearPendingOperation(2);assert.equal(pendingOperation(2),null);assert.equal(pendingOperation(1).key,first.key);}finally{globalThis.fetch=previousFetch;globalThis.sessionStorage=previousStorage;}
});
test("Pending operation persists only a hash, preserves idempotency and migrates old signatures", async () => {
  const previousFetch = globalThis.fetch,
    previousStorage = globalThis.sessionStorage;
  const map = new Map();
  globalThis.sessionStorage = {
    getItem: (key) => map.get(key) || null,
    setItem: (key, value) => map.set(key, value),
    removeItem: (key) => map.delete(key),
  };
  const keys = [];
  globalThis.fetch = async (_url, options) => {
    keys.push(options.headers["Idempotency-Key"]);
    return new Response(JSON.stringify({ message: "Temporary failure" }), {
      status: 503,
    });
  };
  try {
    const payload = {
      currentPassword: "SecretOld123!",
      password: "SecretNew123!",
    };
    await assert.rejects(operation("changePassword", payload));
    const pending = map.get("fitgate-pending");
    assert.ok(!pending.includes("Secret"));
    assert.match(JSON.parse(pending).signature, /^[a-f0-9]{64}$/);
    await assert.rejects(operation("changePassword", payload));
    assert.equal(keys[0], keys[1]);
    await assert.rejects(
      operation("changePassword", { ...payload, password: "Different123!" }),
      /belirsiz/,
    );
    map.set(
      "fitgate-pending",
      JSON.stringify({
        signature: JSON.stringify({ type: "changePassword", payload }),
        key: keys[0],
      }),
    );
    await assert.rejects(operation("changePassword", payload));
    assert.ok(!map.get("fitgate-pending").includes("Secret"));
    assert.equal(keys[2], keys[0]);
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ ok: true }), { status: 200 });
    await operation("changePassword", payload);
    assert.equal(map.has("fitgate-pending"), false);
  } finally {
    globalThis.fetch = previousFetch;
    globalThis.sessionStorage = previousStorage;
  }
});
