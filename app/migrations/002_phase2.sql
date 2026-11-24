CREATE TABLE reviews (
  question_id INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
  due_at TEXT NOT NULL,
  interval_days INTEGER NOT NULL,
  streak INTEGER NOT NULL DEFAULT 0,
  reason TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_reviews_due ON reviews(due_at);

CREATE TABLE question_concepts (
  question_id INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
  concept TEXT NOT NULL,
  model TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE study_materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  level TEXT NOT NULL,
  content TEXT NOT NULL,
  model TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (question_id, level)
);

CREATE TABLE study_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  verification_question_id INTEGER REFERENCES questions(id) ON DELETE SET NULL,
  session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
  outcome TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_study_records_q ON study_records(question_id);

CREATE TABLE tutor_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user','model')),
  content TEXT NOT NULL,
  model TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_tutor_thread ON tutor_messages(thread, id);

CREATE TABLE ai_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feature TEXT NOT NULL,
  model TEXT,
  ok INTEGER NOT NULL,
  error TEXT,
  input_chars INTEGER,
  output_chars INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE pdf_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  subject_hint TEXT,
  chunks_total INTEGER NOT NULL DEFAULT 0,
  chunks_done INTEGER NOT NULL DEFAULT 0,
  n_questions INTEGER NOT NULL DEFAULT 0,
  n_omitted INTEGER NOT NULL DEFAULT 0,
  warnings TEXT NOT NULL DEFAULT '[]',
  result TEXT,
  imported_at TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);
