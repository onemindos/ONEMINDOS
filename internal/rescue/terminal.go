// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"html/template"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// The owner-only web terminal (SEC-TERM-01, D-014). It lives only here, in the
// rescue console's own process: it is not in the gateway, the OpenAPI document,
// the SDK or the MCP tools, so no agent surface can reach it.
//
// Every one of these must hold before a shell opens, checked in this order:
//
//  1. the caller is the owner (the console's own check; a valid non-owner
//     credential, such as an agent token, gets 403, never a shell);
//  2. the switch file exists (off by default; `onemindd rescue terminal enable`);
//  3. a fresh passkey assertion (Reauth), checked by the gateway (passkey.go),
//     once per session, at the start. D-014 forbids a shell behind the plain
//     owner token. With no Reauth wired, or the gateway unreachable, step 3
//     refuses with 503, and with an assertion that does not verify, 401;
//  4. the start event is on the audit chain (fail closed: no record, no shell).
//
// Keystrokes and output are NOT recorded, only who, when, from where, how long
// and how many bytes. The chain is append-only and cannot be edited, so a
// password typed into a shell would sit in it for good; and a recording
// readable by whoever reads the log is a second way to learn secrets. The start
// and end lines are the accountability. See docs/security/rescue-terminal.md.

// Session is one running shell.
type Session interface {
	io.ReadWriteCloser
	// Done is closed when the shell has exited.
	Done() <-chan struct{}
}

// Spawner starts a shell (the real one is a PTY, pty_linux.go).
type Spawner interface {
	Spawn() (Session, error)
}

// Reauther proves a fresh passkey assertion for this request and names the credential.
type Reauther interface {
	Fresh(r *http.Request) (credential string, err error)
}

// ErrNoFreshAuth means the passkey step failed or is not available.
var ErrNoFreshAuth = errors.New("a fresh passkey sign-in is required")

// Terminal configures the terminal routes. Leave Config.Terminal nil to not mount them.
type Terminal struct {
	// SwitchFile enables the terminal when it exists as a regular file nobody but
	// its owner can write. Absent means off.
	SwitchFile string
	Reauth     Reauther // nil: refuse every start (503); production wires a GatewayReauth
	Spawner    Spawner
	Audit      *Audit
	// IdleTimeout closes a session nobody types into; MaxDuration is the hard cap.
	IdleTimeout, MaxDuration time.Duration
}

// SwitchOn reports whether the switch file is present and not group/world writable.
func SwitchOn(path string) bool {
	st, err := os.Stat(path)
	return err == nil && st.Mode().IsRegular() && st.Mode().Perm()&0o022 == 0
}

type termSession struct {
	id       string
	sess     Session
	started  time.Time
	client   string
	cred     string
	owner    [32]byte // sha256 of the owner token that started it: only that credential may use the session
	bytesIn  atomic.Int64
	bytesOut atomic.Int64
	tmu      sync.Mutex // guards idle and max, which a timer may fire before they are stored
	idle     *time.Timer
	max      *time.Timer
	once     sync.Once
}

type termState struct {
	mu     sync.Mutex
	active *termSession
}

func (s *Server) mountTerminal() {
	s.mux.HandleFunc("GET /terminal", s.termPage)
	s.mux.HandleFunc("POST /terminal/passkey/options", s.termChallenge)
	s.mux.HandleFunc("POST /terminal/sessions", s.termStart)
	s.mux.HandleFunc("GET /terminal/sessions/{id}/out", s.termOut)
	s.mux.HandleFunc("POST /terminal/sessions/{id}/in", s.termIn)
	s.mux.HandleFunc("POST /terminal/sessions/{id}/close", s.termClose)
}

func isTerminalPath(p string) bool { return p == "/terminal" || strings.HasPrefix(p, "/terminal/") }

var ownerPrincipal = map[string]any{"kind": "person", "role": "owner"}

// deniedNonOwner is called for a valid credential that is not the owner's.
func (s *Server) deniedNonOwner(w http.ResponseWriter, r *http.Request) {
	if t := s.cfg.Terminal; t != nil && t.Audit != nil {
		_ = t.Audit.Append("terminal.denied", map[string]any{"kind": "non-owner"},
			map[string]any{"client": clientIP(r), "path": r.URL.Path, "reason": "not the owner"})
	}
	s.cfg.Logger.Warn("rescue: terminal refused for a non-owner credential", "client", clientIP(r))
	http.Error(w, "the terminal is for the owner only", http.StatusForbidden)
}

// termGuard runs check 2 and, when fresh is set, check 3, and returns the passkey credential. Only the
// start asks for a fresh assertion; the page, the challenge and the calls on an open session need the switch,
// a wired Reauth and (for a session) the owner credential that started it.
func (s *Server) termGuard(w http.ResponseWriter, r *http.Request, fresh bool) (string, bool) {
	t := s.cfg.Terminal
	if !SwitchOn(t.SwitchFile) {
		http.Error(w, "the terminal is off (the owner turns it on with: onemindd rescue terminal enable)", http.StatusNotFound)
		return "", false
	}
	if t.Reauth == nil {
		http.Error(w, "the terminal needs passkey sign-in, which this console is not set up for", http.StatusServiceUnavailable)
		return "", false
	}
	if !fresh {
		return "", true
	}
	cred, err := t.Reauth.Fresh(r)
	switch {
	case errors.Is(err, ErrReauthUnavailable):
		http.Error(w, err.Error(), http.StatusServiceUnavailable)
		return "", false
	case err != nil || cred == "":
		http.Error(w, ErrNoFreshAuth.Error(), http.StatusUnauthorized)
		return "", false
	}
	return cred, true
}

// termChallenge hands the page the gateway's passkey challenge. It opens nothing.
func (s *Server) termChallenge(w http.ResponseWriter, r *http.Request) {
	if !s.sameOriginPost(w, r) {
		return
	}
	if _, ok := s.termGuard(w, r, false); !ok {
		return
	}
	ch, ok := s.cfg.Terminal.Reauth.(Challenger)
	if !ok {
		http.Error(w, "the terminal needs passkey sign-in, which this console is not set up for", http.StatusServiceUnavailable)
		return
	}
	b, err := ch.Challenge(r)
	switch {
	case errors.Is(err, ErrNoPasskey):
		http.Error(w, err.Error(), http.StatusConflict)
		return
	case errors.Is(err, ErrNoFreshAuth):
		http.Error(w, err.Error(), http.StatusUnauthorized)
		return
	case err != nil:
		http.Error(w, ErrReauthUnavailable.Error(), http.StatusServiceUnavailable)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write(b)
}

var termTmpl = template.Must(template.New("t").Parse(`<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>OneMind rescue terminal</title>
<body style="font-family:sans-serif;max-width:60em;margin:1em auto;padding:0 1em">
<h1>Rescue terminal</h1>
<p>A root shell on this box. The session start and end are written to the audit chain (not what you type).
It closes after a few idle minutes. <a href="./">Back</a></p>
<form id="kit" hidden><label>Owner recovery key from the printed kit <input id="kitkey" type="password" autocomplete="off" spellcheck="false" style="width:30em"></label>
<button>Open with the kit</button></form>
<pre id="out" style="background:#111;color:#eee;padding:.5em;min-height:20em;overflow:auto" aria-live="off"></pre>
<form id="f"><input id="line" autocomplete="off" style="width:70%" aria-label="command">
<button>Send</button> <button type="button" id="int">Ctrl-C</button> <button type="button" id="end">End session</button></form>
<script nonce="{{.Nonce}}">
(async()=>{
const out=document.getElementById('out'),line=document.getElementById('line');
const h={'X-CSRF-Token':'{{.CSRF}}'};
const u=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'==='.slice((s.length+3)%4)),c=>c.charCodeAt(0));
const b=a=>btoa(String.fromCharCode(...new Uint8Array(a))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const atBox={{.AtBox}};
const kitForm=document.getElementById('kit'),kitKey=document.getElementById('kitkey');
const kitProof=()=>new Promise(res=>{kitForm.hidden=false;kitKey.focus();
 kitForm.onsubmit=e=>{e.preventDefault();const v=kitKey.value;kitKey.value='';kitForm.hidden=true;res({kit_key:v})}});
out.textContent='Touch your passkey to open the shell...';
let proof;
try{
 const o=await fetch('terminal/passkey/options',{method:'POST',headers:h});
 if(!o.ok){out.textContent='Could not start the passkey check: '+(await o.text());return}
 const opts=await o.json(),pk=opts.publicKey;
 if(!pk){
  if(!atBox){out.textContent='No passkey is registered. Open this page in a browser on the box itself and type the printed emergency kit key.';return}
  out.textContent='No passkey is registered. Type the owner recovery key from your printed emergency kit.';
  proof=await kitProof();
 }else{
  pk.challenge=u(pk.challenge);(pk.allowCredentials||[]).forEach(c=>{c.id=u(c.id)});
  const c=await navigator.credentials.get({publicKey:pk}),x=c.response;
  proof={webauthn:{id:c.id,rawId:b(c.rawId),type:c.type,response:{clientDataJSON:b(x.clientDataJSON),authenticatorData:b(x.authenticatorData),
   signature:b(x.signature),userHandle:x.userHandle?b(x.userHandle):null}}};
 }
}catch(e){out.textContent='Passkey check failed: '+e.message;return}
const r=await fetch('terminal/sessions',{method:'POST',headers:{...h,'Content-Type':'application/json'},body:JSON.stringify(proof)});
if(!r.ok){out.textContent='Could not open a shell: '+(await r.text());return}
out.textContent='';
const {id}=await r.json();
const send=b=>fetch('terminal/sessions/'+id+'/in',{method:'POST',headers:h,body:b});
document.getElementById('f').onsubmit=e=>{e.preventDefault();send(line.value+'\n');line.value=''};
document.getElementById('int').onclick=()=>send('\x03');
document.getElementById('end').onclick=()=>fetch('terminal/sessions/'+id+'/close',{method:'POST',headers:h});
const rd=(await fetch('terminal/sessions/'+id+'/out',{headers:h})).body.getReader(),dec=new TextDecoder();
for(;;){const {done,value}=await rd.read();if(done)break;
 out.textContent+=dec.decode(value,{stream:true}).replace(/\x1b\[[0-9;?]*[ -\/]*[@-~]/g,'');out.scrollTop=out.scrollHeight}
out.textContent+='\n[session ended]';
})();
</script></body></html>`))

func nonce() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func (s *Server) termPage(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.termGuard(w, r, false); !ok {
		return
	}
	n := nonce()
	w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-"+n+
		"'; connect-src 'self'; frame-ancestors 'none'")
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_ = termTmpl.Execute(w, map[string]any{"Nonce": n, "CSRF": s.csrf, "AtBox": loopbackClient(r)})
}

// sameOriginPost refuses cross-site writes: the CSRF header must match and any Origin must be ours.
func (s *Server) sameOriginPost(w http.ResponseWriter, r *http.Request) bool {
	if o := r.Header.Get("Origin"); o != "" && o != "https://"+r.Host && o != "http://"+r.Host {
		http.Error(w, "cross-site request refused", http.StatusForbidden)
		return false
	}
	if subtle.ConstantTimeCompare([]byte(r.Header.Get("X-CSRF-Token")), []byte(s.csrf)) != 1 {
		http.Error(w, "csrf token required", http.StatusForbidden)
		return false
	}
	return true
}

func (s *Server) termStart(w http.ResponseWriter, r *http.Request) {
	if !s.sameOriginPost(w, r) {
		return
	}
	t := s.cfg.Terminal
	s.term.mu.Lock()
	defer s.term.mu.Unlock()
	if s.term.active != nil { // checked before the passkey, so a refused start does not spend an assertion
		http.Error(w, "a terminal session is already open", http.StatusConflict)
		return
	}
	cred, ok := s.termGuard(w, r, true)
	if !ok {
		return
	}
	ts := &termSession{id: nonce(), started: s.cfg.Now(), client: clientIP(r), cred: cred, owner: sha256.Sum256([]byte(presented(r)))}
	// Fail closed: no audit line, no shell.
	if err := t.Audit.Append("terminal.start", ownerPrincipal, map[string]any{
		"session": ts.id, "client": ts.client, "credential": cred}); err != nil {
		s.cfg.Logger.Error("rescue: terminal not started, audit write failed", "err", err)
		http.Error(w, "the audit log cannot be written, so no shell is opened", http.StatusInternalServerError)
		return
	}
	sess, err := t.Spawner.Spawn()
	if err != nil {
		_ = t.Audit.Append("terminal.end", ownerPrincipal, map[string]any{
			"session": ts.id, "reason": "spawn-failed", "bytes_in": 0, "bytes_out": 0, "seconds": 0})
		http.Error(w, "could not start a shell: "+err.Error(), http.StatusInternalServerError)
		return
	}
	ts.sess = sess
	ts.tmu.Lock()
	if t.IdleTimeout > 0 {
		ts.idle = time.AfterFunc(t.IdleTimeout, func() { s.termEnd(ts, "idle-timeout") })
	}
	if t.MaxDuration > 0 {
		ts.max = time.AfterFunc(t.MaxDuration, func() { s.termEnd(ts, "max-duration") })
	}
	ts.tmu.Unlock()
	go func() { <-sess.Done(); s.termEnd(ts, "shell-exited") }()
	s.term.active = ts
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"id": ts.id})
}

// termEnd closes the session once and writes its end line.
func (s *Server) termEnd(ts *termSession, reason string) {
	ts.once.Do(func() {
		ts.tmu.Lock()
		if ts.idle != nil {
			ts.idle.Stop()
		}
		if ts.max != nil {
			ts.max.Stop()
		}
		ts.tmu.Unlock()
		_ = ts.sess.Close()
		s.term.mu.Lock()
		if s.term.active == ts {
			s.term.active = nil
		}
		s.term.mu.Unlock()
		err := s.cfg.Terminal.Audit.Append("terminal.end", ownerPrincipal, map[string]any{
			"session": ts.id, "reason": reason, "bytes_in": ts.bytesIn.Load(), "bytes_out": ts.bytesOut.Load(),
			"seconds": int(s.cfg.Now().Sub(ts.started).Seconds())})
		if err != nil {
			s.cfg.Logger.Error("rescue: terminal end not audited", "session", ts.id, "err", err)
		}
	})
}

// session finds the open session named in the URL (checks 1 to 3 have passed).
func (s *Server) session(w http.ResponseWriter, r *http.Request) *termSession {
	s.term.mu.Lock()
	ts := s.term.active
	s.term.mu.Unlock()
	if ts == nil || r.PathValue("id") != ts.id || sha256.Sum256([]byte(presented(r))) != ts.owner {
		http.Error(w, "no such terminal session", http.StatusNotFound)
		return nil
	}
	return ts
}

func (s *Server) touch(ts *termSession) {
	ts.tmu.Lock()
	defer ts.tmu.Unlock()
	if ts.idle != nil {
		ts.idle.Reset(s.cfg.Terminal.IdleTimeout)
	}
}

func (s *Server) termIn(w http.ResponseWriter, r *http.Request) {
	if !s.sameOriginPost(w, r) {
		return
	}
	if _, ok := s.termGuard(w, r, false); !ok {
		return
	}
	ts := s.session(w, r)
	if ts == nil {
		return
	}
	b, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 4096))
	if err != nil {
		http.Error(w, "input too large", http.StatusRequestEntityTooLarge)
		return
	}
	n, err := ts.sess.Write(b)
	ts.bytesIn.Add(int64(n))
	s.touch(ts)
	if err != nil {
		http.Error(w, "session closed", http.StatusGone)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) termOut(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.termGuard(w, r, false); !ok {
		return
	}
	ts := s.session(w, r)
	if ts == nil {
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	fl, _ := w.(http.Flusher)
	buf := make([]byte, 4096)
	for {
		n, err := ts.sess.Read(buf)
		if n > 0 {
			ts.bytesOut.Add(int64(n))
			_, _ = w.Write(buf[:n])
			if fl != nil {
				fl.Flush()
			}
			s.touch(ts)
		}
		if err != nil || r.Context().Err() != nil {
			return
		}
	}
}

func (s *Server) termClose(w http.ResponseWriter, r *http.Request) {
	if !s.sameOriginPost(w, r) {
		return
	}
	if _, ok := s.termGuard(w, r, false); !ok {
		return
	}
	ts := s.session(w, r)
	if ts == nil {
		return
	}
	s.termEnd(ts, "owner-closed")
	w.WriteHeader(http.StatusNoContent)
}
