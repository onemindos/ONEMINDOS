// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type copyStore interface {
	put(context.Context, string, []byte) error // create only
	get(context.Context, string, int64) ([]byte, error)
	records(context.Context) ([]string, error)
	close()
}

type s3CopyStore struct {
	client    *minio.Client
	transport *http.Transport
	bucket    string
	prefix    string
}

func (s s3CopyStore) close() { s.transport.CloseIdleConnections() }

func (s s3CopyStore) put(ctx context.Context, key string, data []byte) error {
	opts := minio.PutObjectOptions{DisableMultipart: true}
	opts.SetMatchETagExcept("*")
	_, err := s.client.PutObject(ctx, s.bucket, s.prefix+key, bytes.NewReader(data), int64(len(data)), opts)
	if minio.ToErrorResponse(err).Code == "PreconditionFailed" {
		return os.ErrExist
	}
	return err
}

func (s s3CopyStore) get(ctx context.Context, key string, max int64) ([]byte, error) {
	f, err := s.client.GetObject(ctx, s.bucket, s.prefix+key, minio.GetObjectOptions{})
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return readCopyObject(f, max)
}

func (s s3CopyStore) records(ctx context.Context) ([]string, error) {
	var ids []string
	for object := range s.client.ListObjects(ctx, s.bucket, minio.ListObjectsOptions{Prefix: s.prefix, Recursive: true}) {
		if object.Err != nil {
			return nil, object.Err
		}
		id, leaf, _ := strings.Cut(strings.TrimPrefix(object.Key, s.prefix), "/")
		if leaf == "complete.json" && copyID(id) {
			ids = append(ids, id)
		}
	}
	return ids, nil
}

func readCopyObject(r io.Reader, max int64) ([]byte, error) {
	b, err := io.ReadAll(io.LimitReader(r, max+1))
	if int64(len(b)) > max {
		return nil, errors.New("copy object exceeds the size limit")
	}
	return b, err
}

func (a *Agent) openCopyStore(t Target, box string, write bool) (copyStore, error) {
	prefix := "boxes/" + box + "/copies"
	switch t.Kind {
	case KindUSB:
		mount := filepath.Join(t.MountRoot, t.USBUUID)
		if mounted, err := a.IsMount(mount); !t.AllowNonMountDir && (err != nil || !mounted) {
			return nil, errors.New("backup destination is not mounted")
		}
		return openNASCopyStore(mount, box, write)
	case KindS3:
		u, err := url.Parse(t.Endpoint)
		if err != nil || (u.Scheme != "https" && u.Scheme != "http") || u.Host == "" ||
			u.User != nil || (u.Path != "" && u.Path != "/") || u.RawPath != "" ||
			u.ForceQuery || u.RawQuery != "" || strings.Contains(t.Endpoint, "#") {
			return nil, errors.New("invalid S3 endpoint")
		}
		access, err := readSecret(t.AccessKeyFile)
		if err != nil {
			return nil, err
		}
		secret, err := readSecret(t.SecretKeyFile)
		if err != nil {
			return nil, err
		}
		transport, err := minio.DefaultTransport(u.Scheme == "https")
		if err != nil {
			return nil, err
		}
		transport.Proxy = nil // owner endpoint only
		client, err := minio.New(u.Host, &minio.Options{
			Creds: credentials.NewStaticV4(access, secret, ""), Secure: u.Scheme == "https",
			Region: t.Region, BucketLookup: minio.BucketLookupPath, Transport: transport,
		})
		if err != nil {
			return nil, err
		}
		if p := strings.Trim(t.Prefix, "/"); p != "" {
			prefix = p + "/" + prefix
		}
		return s3CopyStore{client, transport, t.Bucket, prefix + "/"}, nil
	}
	return nil, fmt.Errorf("unsupported copy destination kind %q", t.Kind)
}
