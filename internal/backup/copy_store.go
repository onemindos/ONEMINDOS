// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type copyStore interface {
	put(context.Context, string, []byte) error // create only
	get(context.Context, string, int64) ([]byte, error)
	records(context.Context) ([]string, error)
	close()
}

type nasCopyStore struct{ *os.Root }

func (s nasCopyStore) close() { _ = s.Close() }

func (s nasCopyStore) put(_ context.Context, key string, data []byte) error {
	dir := path.Dir(key)
	if err := s.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	tmp := dir + "/." + NewRunID(time.Now().UTC())
	f, err := s.OpenFile(tmp, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	defer s.Remove(tmp)
	_, err = f.Write(data)
	if err = errors.Join(err, f.Sync(), f.Close()); err != nil {
		return err
	}
	linkErr := s.Link(tmp, key)
	if linkErr != nil && !errors.Is(linkErr, os.ErrExist) {
		return linkErr
	}
	// Persist the publication and the newly created directories up to the mount.
	for {
		d, err := s.Open(dir)
		if err != nil {
			return err
		}
		if err = errors.Join(d.Sync(), d.Close()); err != nil {
			return err
		}
		if dir == "." {
			return linkErr
		}
		dir = path.Dir(dir)
	}
}

func (s nasCopyStore) get(_ context.Context, key string, max int64) ([]byte, error) {
	fi, err := s.Lstat(key)
	if err != nil {
		return nil, err
	}
	if !fi.Mode().IsRegular() {
		return nil, errors.New("copy object is not a regular file")
	}
	f, err := s.Open(key)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return readCopyObject(f, max)
}

func (s nasCopyStore) records(_ context.Context) ([]string, error) {
	entries, err := fs.ReadDir(s.FS(), ".")
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var ids []string
	for _, entry := range entries {
		if !entry.IsDir() || !copyID(entry.Name()) {
			continue
		}
		if fi, err := s.Lstat(entry.Name() + "/complete.json"); err == nil && fi.Mode().IsRegular() {
			ids = append(ids, entry.Name())
		} else if err != nil && !errors.Is(err, os.ErrNotExist) {
			return nil, err
		}
	}
	return ids, nil
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
		root, err := os.OpenRoot(mount)
		if err != nil {
			return nil, err
		}
		defer root.Close()
		if write {
			if err := root.MkdirAll(prefix, 0o700); err != nil {
				return nil, err
			}
			for _, name := range []string{path.Dir(prefix), "boxes", "."} {
				dir, err := root.Open(name)
				if err != nil {
					return nil, err
				}
				if err := errors.Join(dir.Sync(), dir.Close()); err != nil {
					return nil, err
				}
			}
		}
		r, err := root.OpenRoot(prefix)
		if err != nil {
			return nil, err
		}
		return nasCopyStore{r}, nil
	case KindS3:
		u, err := url.Parse(t.Endpoint)
		if err != nil || (u.Scheme != "https" && u.Scheme != "http") || u.Host == "" ||
			u.User != nil || (u.Path != "" && u.Path != "/") || u.RawQuery != "" || u.Fragment != "" {
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
