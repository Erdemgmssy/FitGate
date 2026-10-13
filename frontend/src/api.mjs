let csrfToken = "";
let refreshPending = null;
export async function request(path, options = {}, canRefresh = true) {
  const {timeoutMs=15000,...fetchOptions}=options;
  const controller=new AbortController();
  const abort=()=>controller.abort();
  let timedOut=false;
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeoutMs);
  try {
  const response = await fetch(`/api/v1/${path}`, {
    credentials: "include",
    ...fetchOptions,
    signal:controller.signal,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
      ...options.headers,
    },
  });
  const body = await response.json().catch((error) => {
    if (controller.signal.aborted) throw error;
    return {};
  });
  if (response.status === 401 && canRefresh && !["auth/login/", "auth/refresh/", "auth/logout/"].includes(path)) {
    refreshPending ||= (async () => {
      if (!csrfToken) await request("auth/csrf/", {}, false);
      await request("auth/refresh/", { method: "POST" }, false);
    })().finally(() => { refreshPending = null; });
    await refreshPending;
    return request(path, options, false);
  }
  if (!response.ok) {
    if(response.status===401&&path!=='auth/login/'&&typeof window!=='undefined')window.dispatchEvent(new Event('fitgate-session-expired'));
    const error = new Error(
      body.message ||
        body.detail ||
        "Sunucuya erişilemedi. Oturumunuzu kontrol edin.",
    );
    error.status = response.status;
    throw error;
  }
  if (body.csrfToken) csrfToken = body.csrfToken;
  return body;
  } catch (error) {
    if (timedOut) {
      const failure=new Error('Sunucu yanıtı zaman aşımına uğradı. İşlem sonucunu kontrol edin.');
      failure.name='TimeoutError';
      throw failure;
    }
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort',abort);
  }
}
export async function signIn(email, password) {
  await request("auth/csrf/");
  return request("auth/login/", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}
const pendingKey=actorId=>actorId==null?'fitgate-pending':`fitgate-pending:${actorId}`;
export function pendingOperation(actorId){try{return JSON.parse(sessionStorage.getItem(pendingKey(actorId))||'null');}catch{return null;}}
export function clearPendingOperation(actorId){sessionStorage.removeItem(pendingKey(actorId));}
export async function operation(type, payload, actorId) {
  const hash=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),byte=>byte.toString(16).padStart(2,'0')).join('');
  const signature = await hash(JSON.stringify({ type, payload }));
  const key=pendingKey(actorId);
  let pending = pendingOperation(actorId);
  if(pending&&!/^[a-f0-9]{64}$/.test(pending.signature)){pending.signature=await hash(pending.signature);sessionStorage.setItem(key,JSON.stringify(pending));}
  if (pending && pending.signature !== signature)
    throw new Error("Önce sonucu belirsiz olan son işlemi tekrar gönderin.");
  pending ||= { signature, key: crypto.randomUUID() };
  sessionStorage.setItem(key, JSON.stringify(pending));
  try {
    const result = await request(`actions/${type}/`, {
      method: "POST",
      headers: { "Idempotency-Key": pending.key },
      body: JSON.stringify({ payload }),
    });
    sessionStorage.removeItem(key);
    return result;
  } catch (error) {
    if (error.status && error.status < 500)
      sessionStorage.removeItem(key);
    throw error;
  }
}
