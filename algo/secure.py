"""Encryption so nothing derived from DataFirst sits in plain text in the public repo or page.

- The page: AES-GCM, key from PBKDF2-SHA256 (600k rounds). The browser decrypts it with your password.
- State files (picks log, results, GEX history): AES-GCM with one key per run, derived from
  PAGE_PASSWORD + a random salt kept in state/salt.txt.
"""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PAGE_ITER = 600_000
STATE_ITER = 300_000
ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
_state_key = None


def b64(b):
    return base64.b64encode(b).decode()


def unb64(s):
    return base64.b64decode(s)


def password():
    p = (os.getenv("PAGE_PASSWORD") or "").strip()
    return p or None


def _derive(pw, salt, iters):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iters).derive(pw.encode())


# ---------------------------------------------------------------- state files
def _key():
    global _state_key
    if _state_key is None:
        pw = password()
        if not pw:
            return None
        os.makedirs(ROOT, exist_ok=True)
        sp = os.path.join(ROOT, "salt.txt")
        if os.path.exists(sp):
            salt = unb64(open(sp).read().strip())
        else:
            salt = os.urandom(16)
            with open(sp, "w") as f:
                f.write(b64(salt))
        _state_key = _derive(pw, salt, STATE_ITER)
    return _state_key


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = json.dumps(obj, default=str).encode()
    k = _key()
    if k:
        iv = os.urandom(12)
        rec = {"enc": 1, "iv": b64(iv), "ct": b64(AESGCM(k).encrypt(iv, raw, None))}
    else:
        rec = json.loads(raw)
    with open(path, "w") as f:
        json.dump(rec, f)


def load(path):
    """Returns None if missing or if it can't be decrypted (e.g. password changed)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            rec = json.load(f)
    except Exception:
        return None
    if isinstance(rec, dict) and rec.get("enc") == 1:
        k = _key()
        if not k:
            return None
        try:
            return json.loads(AESGCM(k).decrypt(unb64(rec["iv"]), unb64(rec["ct"]), None))
        except Exception:
            print(f"[secure] can't decrypt {os.path.basename(path)} (password changed?) — ignoring it")
            return None
    return rec  # old plain-text file


# ---------------------------------------------------------------- page
def lock_page(html: str, pw: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_derive(pw, salt, PAGE_ITER)).encrypt(iv, html.encode(), None)
    return LOCK_HTML.replace("__SALT__", b64(salt)).replace("__IV__", b64(iv)) \
        .replace("__CT__", b64(ct)).replace("__ITER__", str(PAGE_ITER))


LOCK_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Swing levels · NQ</title>
<style>body{margin:0;background:#E6F1FB;color:#042C53;font:15px/1.5 -apple-system,Segoe UI,Inter,Arial,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center}
.box{background:#fff;border:1px solid #B5D4F4;border-radius:14px;padding:26px 28px;width:min(360px,90vw)}
h1{font-size:18px;margin:0 0 4px;color:#0C447C}p{margin:0 0 14px;font-size:13px;color:#5d84ad}
input[type=password]{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #B5D4F4;border-radius:8px;font-size:15px;margin-bottom:10px}
button{width:100%;background:#378ADD;color:#fff;border:0;border-radius:8px;padding:10px;font-size:15px;cursor:pointer}
label{font-size:13px;color:#185FA5;display:flex;gap:6px;align-items:center;margin-bottom:12px}.err{color:#A32D2D;font-size:13px;min-height:18px;margin-top:8px}</style></head>
<body><form class="box" id="f"><h1>Swing levels · NQ</h1><p>Enter your password to open.</p>
<input type="password" id="pw" autocomplete="current-password" autofocus>
<label><input type="checkbox" id="rem" checked> Remember on this device</label>
<button type="submit" id="go">Open</button><div class="err" id="err"></div></form>
<script>
const SALT="__SALT__",IV="__IV__",CT="__CT__",ITER=__ITER__;
const u=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function open_(pw){
  const base=await crypto.subtle.importKey("raw",new TextEncoder().encode(pw),"PBKDF2",false,["deriveKey"]);
  const key=await crypto.subtle.deriveKey({name:"PBKDF2",salt:u(SALT),iterations:ITER,hash:"SHA-256"},base,{name:"AES-GCM",length:256},false,["decrypt"]);
  const pt=await crypto.subtle.decrypt({name:"AES-GCM",iv:u(IV)},key,u(CT));
  const html=new TextDecoder().decode(pt);
  document.open();document.write(html);document.close();
}
function saved(){try{return localStorage.getItem("lv_pw")}catch(e){return null}}
async function tryOpen(pw,remember){
  try{await open_(pw);try{remember?localStorage.setItem("lv_pw",pw):localStorage.removeItem("lv_pw")}catch(e){}}
  catch(e){document.getElementById("err").textContent="Wrong password.";try{localStorage.removeItem("lv_pw")}catch(e){}}
}
document.getElementById("f").addEventListener("submit",e=>{e.preventDefault();
  document.getElementById("go").textContent="Opening…";
  tryOpen(document.getElementById("pw").value,document.getElementById("rem").checked)
    .finally(()=>{const b=document.getElementById("go");if(b)b.textContent="Open"});});
const s=saved();if(s)tryOpen(s,true);
</script></body></html>"""
