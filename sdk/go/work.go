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
	ID           string      `json:"id"`
	ProjectID    string      `json:"project_id"`
	Revision     int         `json:"revision"`
	Title        string      `json:"title"`
	Body         string      `json:"body"`
	Status       string      `json:"status"`
	Priority     int         `json:"priority"`
	Labels       []string    `json:"labels"`
	DueAt        *time.Time  `json:"due_at"`
	SectionID    *string     `json:"section_id"`
	Repeat       *WorkRepeat `json:"repeat"`
	Dependencies []string    `json:"dependencies"`
}

// WorkRepeat is a repeat rule: every day, weekday, week, month or year, every Interval of them.
type WorkRepeat struct {
	Every    string `json:"every"`
	Interval int    `json:"interval"`
	// Tz is the IANA zone the repeat days are counted in; empty means UTC.
	Tz string `json:"tz,omitempty"`
}

// WorkSection groups the tasks of one project.
type WorkSection struct {
	ID        string `json:"id"`
	ProjectID string `json:"project_id"`
	Name      string `json:"name"`
	Position  int    `json:"position"`
}

// WorkComment is a note on a task.
type WorkComment struct {
	ID        string    `json:"id"`
	AuthorID  string    `json:"author_id"`
	Body      string    `json:"body"`
	CreatedAt time.Time `json:"created_at"`
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
func (s *WorkService) List(ctx context.Context, view, project, tz string, limit int) ([]WorkTask, error) {
	q := url.Values{}
	if view != "" {
		q.Set("view", view)
	}
	if project != "" {
		q.Set("project_id", project)
	}
	if tz != "" {
		q.Set("tz", tz)
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

// WorkProject is a Work project as /v1/work/projects returns it.
type WorkProject struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	AIAccess string `json:"ai_access"`
}

// WorkParsed is what quick-add would file for a line of text (operation work.parse). Nothing is created.
type WorkParsed struct {
	Title        string      `json:"title"`
	Project      *string     `json:"project"`
	ProjectID    *string     `json:"project_id"`
	ProjectFound bool        `json:"project_found"`
	Labels       []string    `json:"labels"`
	Repeat       *WorkRepeat `json:"repeat"`
	Priority     *int        `json:"priority"`
	Assignee     *string     `json:"assignee"`
	DueAt        *time.Time  `json:"due_at"`
	DueAllDay    bool        `json:"due_all_day"`
}

// WorkActivity is one line of a task's history: which fields changed, never their values.
type WorkActivity struct {
	ID      int       `json:"id"`
	ActorID string    `json:"actor_id"`
	Kind    string    `json:"kind"`
	Fields  []string  `json:"fields"`
	At      time.Time `json:"at"`
}

func projectPath(id string) string { return "/v1/work/projects/" + url.PathEscape(id) }

// Projects is operation work.projects_list.
func (s *WorkService) Projects(ctx context.Context) ([]WorkProject, error) {
	var v []WorkProject
	return v, s.c.Do(ctx, http.MethodGet, "/v1/work/projects", nil, &v)
}

// UpdateProject is operation work.project_update. An empty name or access leaves that field alone.
func (s *WorkService) UpdateProject(ctx context.Context, id, name, aiAccess string) (*WorkProject, error) {
	body := map[string]string{}
	if name != "" {
		body["name"] = name
	}
	if aiAccess != "" {
		body["ai_access"] = aiAccess
	}
	var p WorkProject
	return &p, s.c.Do(ctx, http.MethodPatch, projectPath(id), body, &p)
}

// DeleteProject is operation work.project_delete. Its tasks go with it.
func (s *WorkService) DeleteProject(ctx context.Context, id string) error {
	return s.c.Do(ctx, http.MethodDelete, projectPath(id), nil, nil)
}

// AddMember is operation work.member_add (the project creator only).
func (s *WorkService) AddMember(ctx context.Context, project, person string) error {
	return s.c.Do(ctx, http.MethodPut, projectPath(project)+"/members/"+url.PathEscape(person), nil, nil)
}

// RemoveMember is operation work.member_remove (the project creator only).
func (s *WorkService) RemoveMember(ctx context.Context, project, person string) error {
	return s.c.Do(ctx, http.MethodDelete, projectPath(project)+"/members/"+url.PathEscape(person), nil, nil)
}

// Parse is operation work.parse: a preview of quick-add.
func (s *WorkService) Parse(ctx context.Context, text, tz string) (*WorkParsed, error) {
	body := map[string]string{"text": text}
	if tz != "" {
		body["tz"] = tz
	}
	var p WorkParsed
	return &p, s.c.Do(ctx, http.MethodPost, "/v1/work/parse", body, &p)
}

// Activity is operation work.task_activity, newest first.
func (s *WorkService) Activity(ctx context.Context, project, task string) ([]WorkActivity, error) {
	var v []WorkActivity
	return v, s.c.Do(ctx, http.MethodGet, projectPath(project)+"/tasks/"+url.PathEscape(task)+"/activity", nil, &v)
}

func taskPath(project, task string) string {
	return projectPath(project) + "/tasks/" + url.PathEscape(task)
}

func keyed(key string) map[string]string {
	if key == "" {
		key = NewIdempotencyKey()
	}
	return map[string]string{"Idempotency-Key": key}
}

// Comments is operation work.comments_list, oldest first.
func (s *WorkService) Comments(ctx context.Context, project, task string) ([]WorkComment, error) {
	var v []WorkComment
	return v, s.c.Do(ctx, http.MethodGet, taskPath(project, task)+"/comments", nil, &v)
}

// AddComment is operation work.comment_add. A retry with the same key returns the same comment.
func (s *WorkService) AddComment(ctx context.Context, project, task, body, key string) (*WorkComment, error) {
	var c WorkComment
	_, err := s.c.do(ctx, request{method: http.MethodPost, path: taskPath(project, task) + "/comments",
		body: map[string]string{"body": body}, retry: true, headers: keyed(key)}, &c)
	return &c, err
}

// DeleteComment is operation work.comment_delete (the author only).
func (s *WorkService) DeleteComment(ctx context.Context, project, task, id string) error {
	return s.c.Do(ctx, http.MethodDelete, taskPath(project, task)+"/comments/"+url.PathEscape(id), nil, nil)
}

// Sections is operation work.sections_list.
func (s *WorkService) Sections(ctx context.Context, project string) ([]WorkSection, error) {
	var v []WorkSection
	return v, s.c.Do(ctx, http.MethodGet, projectPath(project)+"/sections", nil, &v)
}

// AddSection is operation work.section_create.
func (s *WorkService) AddSection(ctx context.Context, project, name, key string) (*WorkSection, error) {
	var v WorkSection
	_, err := s.c.do(ctx, request{method: http.MethodPost, path: projectPath(project) + "/sections",
		body: map[string]string{"name": name}, retry: true, headers: keyed(key)}, &v)
	return &v, err
}

// DeleteSection is operation work.section_delete. Its tasks stay in the project.
func (s *WorkService) DeleteSection(ctx context.Context, project, id string) error {
	return s.c.Do(ctx, http.MethodDelete, projectPath(project)+"/sections/"+url.PathEscape(id), nil, nil)
}
