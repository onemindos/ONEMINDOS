Fixtures for internal/hostext, made once with OpenSSL (the private keys were thrown away, nothing here can sign):

    openssl req -x509 -newkey rsa:2048 -nodes -keyout rsa.key -out rsa.crt -days 36500 -subj "/CN=OneMind test sysext key (fixture only)"
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout ec.key -out ec.crt -days 36500 -subj "/CN=OneMind test ec key (fixture only)"
    printf '%s' "$(openssl rand -hex 32)" > roothash
    openssl smime -sign -nocerts -noattr -binary -in roothash -inkey rsa.key -signer rsa.crt -outform der -out rsa-noattr.p7s
    openssl smime -sign -nocerts -binary -in roothash -inkey ec.key -signer ec.crt -outform der -out ec-attr.p7s -md sha256

rsa-noattr.p7s is the form the kernel's dm-verity signature check documents (no signed attributes);
ec-attr.p7s carries signed attributes (messageDigest), the other form a signer may produce.
