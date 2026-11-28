module github.com/onemindos/onemindos

go 1.26.0

require (
	github.com/Masterminds/semver/v3 v3.3.1
	github.com/dlclark/regexp2 v1.11.5
	github.com/google/go-containerregistry v0.20.7
	github.com/nats-io/nats-server/v2 v2.15.3
	github.com/nats-io/nats.go v1.55.0
	github.com/nats-io/nkeys v0.4.17
	github.com/santhosh-tekuri/jsonschema/v6 v6.0.2
	github.com/sigstore/sigstore v1.10.6
	github.com/theupdateframework/go-tuf/v2 v2.4.2
	golang.org/x/net v0.60.0
)

require (
	github.com/apapsch/go-jsonmerge/v2 v2.0.0 // indirect
	github.com/containerd/stargz-snapshotter/estargz v0.18.1 // indirect
	github.com/cpuguy83/go-md2man/v2 v2.0.7 // indirect
	github.com/google/uuid v1.5.0 // indirect
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/oapi-codegen/runtime v1.1.2 // indirect
	github.com/opencontainers/image-spec v1.1.1 // indirect
	github.com/russross/blackfriday/v2 v2.1.0 // indirect
	github.com/vbatts/tar-split v0.12.2 // indirect
	go.yaml.in/yaml/v3 v3.0.4 // indirect
	golang.org/x/sync v0.24.0 // indirect
	golang.org/x/text v0.43.0 // indirect
)

require (
	github.com/antithesishq/antithesis-sdk-go v0.9.0-default-no-op // indirect
	github.com/cenkalti/backoff/v5 v5.0.3 // indirect
	github.com/google/go-tpm v0.9.8 // indirect
	github.com/klauspost/compress v1.20.4 // indirect
	github.com/minio/highwayhash v1.0.4 // indirect
	github.com/nats-io/jwt/v2 v2.8.3 // indirect
	github.com/nats-io/nuid v1.0.1 // indirect
	github.com/onemindos/onemindos/sdk/go v0.0.0
	github.com/opencontainers/go-digest v1.0.0 // indirect
	github.com/secure-systems-lab/go-securesystemslib v0.11.0 // indirect
	github.com/sigstore/protobuf-specs v0.5.0 // indirect
	github.com/spf13/cobra v1.10.2
	github.com/spf13/pflag v1.0.10
	golang.org/x/crypto v0.58.0 // indirect
	golang.org/x/sys v0.50.0
	golang.org/x/term v0.47.0
	golang.org/x/time v0.16.0 // indirect
	google.golang.org/genproto/googleapis/api v0.0.0-20250825161204-c5933d9347a5 // indirect
	google.golang.org/protobuf v1.36.11 // indirect
	gopkg.in/yaml.v3 v3.0.1
)

replace github.com/onemindos/onemindos/sdk/go => ./sdk/go
