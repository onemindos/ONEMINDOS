#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""UMB-ACCT-1 run-2: drive Kanidm's own web UI in headless Chromium with a *virtual WebAuthn authenticator*
(Chrome DevTools WebAuthn domain, through Selenium). Chromium enforces the real RP ID and origin rules, so this
is the closest a headless lab gets to a phone browser. Run it inside a network namespace to pick the access path:
    ip netns exec nsl python3 -I wa.py ...     (LAN path)      ip netns exec nsm python3 -I wa.py ...  (mesh path)
Secrets (reset links, the authenticator's private key) live only in AK_SECRETS (mode 0700); never printed.
"""
import base64, json, os, sys, time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.virtual_authenticator import (Credential, Protocol, Transport,
                                                             VirtualAuthenticatorOptions)
SECRETS = os.environ.get("AK_SECRETS", "/root/aklab/secrets")
SHOTS = os.environ.get("AK_SHOTS", "/root/aklab/shots")


def out(**kw):
    print(json.dumps(kw, sort_keys=True), flush=True)


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64(s):
    s = s.replace("+", "-").replace("/", "_")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def driver():
    o = webdriver.ChromeOptions()
    o.binary_location = "/usr/bin/chromium"
    for a in ("--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
              "--user-data-dir=/tmp/wa-profile-%d" % os.getpid(), "--window-size=1100,900",
              "--lang=en-US", "--disable-features=DnsOverHttps"):
        o.add_argument(a)
    d = webdriver.Chrome(service=webdriver.ChromeService("/usr/bin/chromedriver"), options=o)
    d.set_page_load_timeout(40)
    return d


def add_authenticator(d):
    vo = VirtualAuthenticatorOptions()
    vo.protocol = Protocol.CTAP2
    vo.transport = Transport.INTERNAL
    vo.has_resident_key = True
    vo.has_user_verification = True
    vo.is_user_verified = True
    vo.is_user_consenting = True
    d.add_virtual_authenticator(vo)


def creds_to_json(d):
    res = []
    for c in d.get_credentials():
        # selenium already returns these as base64url strings
        res.append({"id": c.id, "rp_id": c.rp_id, "resident": c.is_resident_credential,
                    "user_handle": c.user_handle, "private_key": c.private_key, "sign_count": c.sign_count})
    return res


def creds_from_json(d, items):
    for it in items:
        d.add_credential(Credential.create_resident_credential(
            unb64(it["id"]), it["rp_id"], unb64(it["user_handle"]), unb64(it["private_key"]), it["sign_count"])
            if it["resident"] else
            Credential.create_non_resident_credential(unb64(it["id"]), it["rp_id"], unb64(it["private_key"]),
                                                      it["sign_count"]))


def shot(d, name):
    os.makedirs(SHOTS, exist_ok=True)
    d.save_screenshot(os.path.join(SHOTS, name + ".png"))


def page(d):
    """A compact, non-secret description of what the page shows."""
    txt = d.find_element(By.TAG_NAME, "body").text.strip().replace("\n", " | ")
    btns = [b.text.strip() or b.get_attribute("id") or b.get_attribute("type") for b in d.find_elements(By.CSS_SELECTOR, "button, input[type=submit], a.btn")]
    inputs = [(i.get_attribute("id") or i.get_attribute("name"), i.get_attribute("type")) for i in d.find_elements(By.TAG_NAME, "input")]
    return {"url": d.current_url.split("?")[0], "text": txt[:300], "buttons": btns, "inputs": inputs}


# ------------------------------------------------------------------ flows
def wait_for(d, fn, what, timeout=20):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r:
                return r
        except Exception as e:  # element not there yet
            last = e
        time.sleep(0.4)
    raise RuntimeError("timeout waiting for %s (%s)\n%s" % (what, last, json.dumps(page(d))))


def click_text(d, text, tag="button"):
    for b in d.find_elements(By.TAG_NAME, tag):
        if b.text.strip().lower() == text.lower() and b.is_displayed():
            b.click()
            return True
    return False


def enrol(base, user, cred_out, expect="ok"):
    """Open the owner's reset link, add a passkey through the UI, save. Returns the exported credential."""
    d = driver()
    try:
        add_authenticator(d)
        tok = open(os.path.join(SECRETS, user + ".reset")).read().strip()
        d.get(base + "/ui/reset?token=" + tok)
        wait_for(d, lambda: click_text(d, "Add Passkey"), "Add Passkey button")
        out(step="open_reset", ok=True, page=page(d)["text"][:120], origin=base)

        def fail(why):
            logs = [l["message"] for l in d.get_log("browser") if "frame-ancestors" not in l["message"]]
            count = len(d.get_credentials())
            forbidden = f"{base}/ui/reset/add_passkey - Failed to load resource: the server responded with a status of 403 (Forbidden)"
            out(step="passkey_created", ok=False, credentials_in_authenticator=count, origin=base,
                why=why, page=page(d)["text"][:240], browser_console=[l[:330] for l in logs[-4:]])
            shot(d, "enrol-failed")
            return expect == "refused" and count == 0 and forbidden in logs
        # the modal asks for a label
        def label():
            for i in d.find_elements(By.CSS_SELECTOR, "input[type=text]"):
                if i.is_displayed():
                    i.clear(); i.send_keys("lab-virtual-authenticator"); return i
        try:
            wait_for(d, label, "passkey label input", timeout=10)
        except RuntimeError as e:
            return fail("no label dialog: " + str(e).split("\n")[0])
        shot(d, "enrol-label")
        wait_for(d, lambda: click_text(d, "Add Passkey") or click_text(d, "Add") or click_text(d, "Submit"), "label submit")
        # the virtual authenticator answers the WebAuthn create() call by itself
        try:
            wait_for(d, lambda: len(d.get_credentials()) > 0, "authenticator to hold a credential", timeout=12)
        except RuntimeError:
            logs = [l["message"][:330] for l in d.get_log("browser") if "frame-ancestors" not in l["message"]][-3:]
            out(step="passkey_created", ok=False, credentials_in_authenticator=0, origin=base,
                page=page(d)["text"][:200], browser_console=logs)
            shot(d, "enrol-failed")
            return False
        time.sleep(1.5)
        out(step="passkey_created", ok=True, credentials_in_authenticator=len(d.get_credentials()),
            rp_id=creds_to_json(d)[0]["rp_id"], origin=base, page=page(d)["text"][:200])
        shot(d, "enrol-after-create")
        wait_for(d, lambda: click_text(d, "Save Changes"), "Save Changes")
        time.sleep(2)
        pg = page(d)
        out(step="saved", ok=True, page=pg["text"][:200])
        shot(d, "enrol-saved")
        cj = creds_to_json(d)
        write_secret(cred_out, json.dumps(cj))
        out(step="credential_exported", ok=True, count=len(cj), credential_fp=fp(cj[0]))
        return expect == "ok"
    finally:
        d.quit()


def fp(c):
    import hashlib
    return hashlib.sha256(unb64(c["id"])).hexdigest()[:16]


def write_secret(name, value):
    os.makedirs(SECRETS, mode=0o700, exist_ok=True)
    p = os.path.join(SECRETS, name)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)


def read_secret(name):
    return open(os.path.join(SECRETS, name)).read()


def signin(base, user, cred_file, expect="ok"):
    """Fresh browser (a new device that has been given the passkey), sign in through the UI."""
    d = driver()
    try:
        add_authenticator(d)
        creds_from_json(d, json.loads(read_secret(cred_file)))
        sc_before = [c["sign_count"] for c in creds_to_json(d)]
        d.get(base + "/ui/login")
        def uname():
            for i in d.find_elements(By.CSS_SELECTOR, "input[type=text], input[name=username], input#username"):
                if i.is_displayed():
                    return i
        u = wait_for(d, uname, "username input")
        u.clear(); u.send_keys(user)
        shot(d, "signin-username")
        out(step="login_page", page=page(d)["text"][:150], origin=base)
        u.submit() if not click_text(d, "Begin") and not click_text(d, "Continue") else None
        # the passkey step: the UI either starts WebAuthn at once or offers a button
        end = time.time() + 25
        result = None
        while time.time() < end:
            time.sleep(1)
            body = d.find_element(By.TAG_NAME, "body").text
            url = d.current_url
            if "/ui/apps" in url or "/ui/profile" in url or "/ui/admin" in url or "Signed in" in body:
                result = "signed-in"; break
            click_text(d, "Use Passkey") or click_text(d, "Passkey")
            if any(k in body.lower() for k in ("login failed", "denied", "invalid webauthn")):
                result = "refused-by-server"; break
        pg = page(d)
        shot(d, "signin-result-" + expect)
        logs = []
        try:
            logs = [l["message"] for l in d.get_log("browser")]
        except Exception:
            pass
        who = None
        if result == "signed-in":
            d.get(base + "/ui/profile")
            time.sleep(1.5)
            who = page(d)["text"][:160]
        # the phone keeps its own signature counter: carry it back so the next device/browser starts from it
        after = creds_to_json(d)
        write_secret(cred_file, json.dumps(after))
        sc = [c["sign_count"] for c in after]
        err = [l for l in logs if "SecurityError" in l or "NotAllowed" in l]
        if result is None and err:
            result = "refused-by-browser"
        out(step="signin", ok=(result == "signed-in"), result=result, url=pg["url"], page=pg["text"][:240],
            profile=who, browser_console=[l[:260] for l in logs[-5:] if "frame-ancestors" not in l][-3:], origin=base,
            sign_count_before=sc_before, sign_count_after=sc, credential_fp=fp(after[0]) if after else None)
        if expect == "refused":
            mismatch = "SecurityError: The relying party ID is not a registrable domain suffix of, nor equal to the current domain"
            return result == "refused-by-browser" and any(mismatch in log for log in logs)
        return result == "signed-in"
    finally:
        d.quit()


def tosoft(user, cred_file):
    """Give the API lab client (aklab.py SoftPasskey) the browser authenticator's key, so one owner passkey is used by both."""
    from cryptography.hazmat.primitives import serialization
    c = json.loads(read_secret(cred_file))[0]
    key = serialization.load_der_private_key(unb64(c["private_key"]), None)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    write_secret(user + ".passkey.json", json.dumps({"rp_id": c["rp_id"], "cred_id": c["id"].rstrip("="), "user_handle": (c["user_handle"] or "").rstrip("="),
                                                    "count": c["sign_count"], "key_pem": pem}))
    out(step="tosoft", ok=True, credential_fp=fp(c), sign_count=c["sign_count"])


def fromsoft(user, cred_file):
    """Carry the signature counter used by the API client back to the browser authenticator's file."""
    s = json.loads(read_secret(user + ".passkey.json"))
    cs = json.loads(read_secret(cred_file))
    cs[0]["sign_count"] = max(cs[0]["sign_count"], s["count"])
    write_secret(cred_file, json.dumps(cs))
    out(step="fromsoft", ok=True, sign_count=cs[0]["sign_count"])


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "enrol":      # enrol <base-url> <user> <cred-file> [ok|refused]
        sys.exit(0 if enrol(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "ok") else 1)
    if c == "tosoft":
        tosoft(sys.argv[2], sys.argv[3]); sys.exit(0)
    if c == "fromsoft":
        fromsoft(sys.argv[2], sys.argv[3]); sys.exit(0)
    if c == "signin":     # signin <base-url> <user> <cred-file> [ok|refused]
        sys.exit(0 if signin(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "ok") else 1)
    print("unknown command"); sys.exit(2)
