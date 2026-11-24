CREATE TABLE exams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE subjects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exam_id INTEGER REFERENCES exams(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_topics_subject ON topics(subject_id);

CREATE TABLE imports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT,
  source TEXT,
  total INTEGER NOT NULL DEFAULT 0,
  imported INTEGER NOT NULL DEFAULT 0,
  duplicates INTEGER NOT NULL DEFAULT 0,
  invalid INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT,
  content_hash TEXT NOT NULL,
  subject_id INTEGER NOT NULL REFERENCES subjects(id),
  import_id INTEGER REFERENCES imports(id) ON DELETE SET NULL,
  bank TEXT,
  year INTEGER,
  organization TEXT,
  exam_name TEXT,
  statement TEXT NOT NULL,
  support_text TEXT,
  alternatives TEXT NOT NULL,
  correct_answer TEXT NOT NULL,
  explanation TEXT,
  difficulty TEXT,
  images TEXT NOT NULL DEFAULT '[]',
  extra TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_questions_hash ON questions(content_hash);
CREATE UNIQUE INDEX uq_questions_external ON questions(external_id) WHERE external_id IS NOT NULL;
CREATE INDEX idx_questions_subject ON questions(subject_id);
CREATE INDEX idx_questions_import ON questions(import_id);

CREATE TABLE question_topics (
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  PRIMARY KEY (question_id, topic_id)
);
CREATE INDEX idx_qt_topic ON question_topics(topic_id);

CREATE TABLE question_flags (
  question_id INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);

CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  reveal TEXT NOT NULL DEFAULT 'each',
  timer_limit_s INTEGER,
  config TEXT NOT NULL DEFAULT '{}',
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_s INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE session_questions (
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  PRIMARY KEY (session_id, question_id)
);

CREATE TABLE answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  chosen TEXT NOT NULL,
  is_correct INTEGER NOT NULL,
  confidence TEXT NOT NULL CHECK (confidence IN ('certeza','duvida','chute')),
  time_s INTEGER NOT NULL DEFAULT 0,
  error_type TEXT,
  error_note TEXT,
  answered_at TEXT NOT NULL,
  UNIQUE (session_id, question_id)
);
CREATE INDEX idx_answers_question ON answers(question_id);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
