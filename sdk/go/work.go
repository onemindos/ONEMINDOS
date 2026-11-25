// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"context"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// WorkTask is a Work task as /v1/work returns it.
type WorkTask struct {
	ID           string     `json:"id"`
	ProjectID    string     `json:"project_id"`
	Revision     int        `json:"revision"`
	Title        string     `json:"title"`
	Body         string     `json:"body"`
	Status       string     `json:"status"`
	Priority     int        `json:"priority"`
	Labels       []string   `json:"labels"`
	DueAt        *time.Time `json:"due_at"`
	Dependencies []string   `json:"dependencies"`
}

// WorkService is the Work tasks API (/v1/work).
type WorkService struct{ c *Client }

// QuickAdd is operation work.quick_add: the gateway reads one line such as
// "Pay rent tomorrow #Home p1" and files the task. An empty key gets a fresh one, and a retry
// with the same key returns the same task instead of adding a second.
func (s *WorkService) QuickAdd(ctx context.Context, text, tz, key string) (*WorkTask, error) {
	if key == "" {
		key = NewIdempotencyKey()
	}
	body := map[string]string{"text": text}
	if tz != "" {
		body["tz"] = tz
	}
	var t WorkTask
	_, err := s.c.do(ctx, request{method: http.MethodPost, path: "/v1/work/quick-add", body: body, retry: true,
		headers: map[string]string{"Idempotency-Key": key}}, &t)
	return &t, err
}

// List is operation work.tasks_list. view is "all", "today", "upcoming" or "inbox"; project may be empty.
func (s *WorkService) List(ctx context.Context, view, project string, limit int) ([]WorkTask, error) {
	q := url.Values{}
	if view != "" {
		q.Set("view", view)
	}
	if project != "" {
		q.Set("project_id", project)
	}
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	var v []WorkTask
	return v, s.c.Do(ctx, http.MethodGet, "/v1/work/tasks?"+q.Encode(), nil, &v)
}

// Complete is operation work.task_update with status "done". It reads the task first for the
// revision the gateway wants in If-Match, so a task edited meanwhile fails with a conflict.
func (s *WorkService) Complete(ctx context.Context, project, id string) (*WorkTask, error) {
	path := "/v1/work/projects/" + url.PathEscape(project) + "/tasks/" + url.PathEscape(id)
	var t WorkTask
	if err := s.c.Do(ctx, http.MethodGet, path, nil, &t); err != nil {
		return nil, err
	}
	_, err := s.c.do(ctx, request{method: http.MethodPatch, path: path, body: map[string]string{"status": "done"},
		headers: map[string]string{"If-Match": strconv.Itoa(t.Revision)}}, &t)
	return &t, err
}
