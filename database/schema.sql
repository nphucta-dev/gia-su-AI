-- Current MySQL schema. Apply only to an empty database.

SET time_zone = '+00:00';

CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

CREATE TABLE subjects (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(120) NOT NULL,
	grade_level VARCHAR(50) NOT NULL,
	is_active BOOL NOT NULL DEFAULT 1,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_subjects_name_grade_level UNIQUE (name, grade_level)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT,
	email VARCHAR(255) NOT NULL,
	password_hash VARCHAR(255) NOT NULL,
	full_name VARCHAR(120) NOT NULL,
	birth_year SMALLINT,
	`role` VARCHAR(10) NOT NULL DEFAULT 'LEARNER',
	is_active BOOL NOT NULL DEFAULT 1,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_users_email UNIQUE (email),
	CONSTRAINT ck_users_role CHECK (role IN ('LEARNER', 'ADMIN'))
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE topics (
	id INTEGER NOT NULL AUTO_INCREMENT,
	subject_id INTEGER NOT NULL,
	chapter_name VARCHAR(150) NOT NULL,
	name VARCHAR(180) NOT NULL,
	description TEXT,
	is_active BOOL NOT NULL DEFAULT 1,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_topics_subject_id_chapter_name_name UNIQUE (subject_id, chapter_name, name),
	FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE INDEX ix_topics_subject_id ON topics (subject_id);

CREATE TABLE chat_sessions (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id INTEGER NOT NULL,
	topic_id INTEGER NOT NULL,
	title VARCHAR(200),
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE INDEX ix_chat_sessions_user_updated_at ON chat_sessions (user_id, updated_at DESC);

CREATE TABLE documents (
	id INTEGER NOT NULL AUTO_INCREMENT,
	topic_id INTEGER NOT NULL,
	title VARCHAR(200) NOT NULL,
	file_path TEXT NOT NULL,
	source_url TEXT,
	status VARCHAR(10) NOT NULL DEFAULT 'pending',
	is_active BOOL NOT NULL DEFAULT 0,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	processed_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_documents_status CHECK (status IN ('pending', 'ready', 'error')),
	FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE learning_progress (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id INTEGER NOT NULL,
	topic_id INTEGER NOT NULL,
	total_quizzes INTEGER NOT NULL DEFAULT 0,
	correct_count INTEGER NOT NULL DEFAULT 0,
	total_count INTEGER NOT NULL DEFAULT 0,
	mastery_percent NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
	last_studied_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_learning_progress_user_id_topic_id UNIQUE (user_id, topic_id),
	CONSTRAINT ck_learning_progress_total_quizzes CHECK (total_quizzes >= 0),
	CONSTRAINT ck_learning_progress_correct_count CHECK (correct_count >= 0),
	CONSTRAINT ck_learning_progress_total_count CHECK (total_count >= 0),
	CONSTRAINT ck_learning_progress_correct_count_total_count CHECK (correct_count <= total_count),
	CONSTRAINT ck_learning_progress_mastery_percent CHECK (mastery_percent BETWEEN 0 AND 100),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE quizzes (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id INTEGER NOT NULL,
	topic_id INTEGER NOT NULL,
	difficulty VARCHAR(10) NOT NULL,
	status VARCHAR(15) NOT NULL DEFAULT 'in_progress',
	score NUMERIC(5, 2),
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	completed_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_quizzes_difficulty CHECK (difficulty IN ('easy', 'medium', 'hard')),
	CONSTRAINT ck_quizzes_status CHECK (status IN ('in_progress', 'completed')),
	CONSTRAINT ck_quizzes_score CHECK (score BETWEEN 0 AND 100),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE INDEX ix_quizzes_user_completed_at ON quizzes (user_id, completed_at DESC);

CREATE TABLE chat_messages (
	id INTEGER NOT NULL AUTO_INCREMENT,
	session_id INTEGER NOT NULL,
	`role` VARCHAR(12) NOT NULL,
	content TEXT NOT NULL,
	hint_level SMALLINT,
	is_full_solution BOOL NOT NULL DEFAULT 0,
	feedback SMALLINT,
	source_refs JSON NOT NULL DEFAULT (JSON_ARRAY()),
	token_count INTEGER,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_chat_messages_role CHECK (role IN ('user', 'assistant')),
	CONSTRAINT ck_chat_messages_hint_level CHECK (hint_level BETWEEN 1 AND 3),
	CONSTRAINT ck_chat_messages_feedback CHECK (feedback IN (-1, 1)),
	CONSTRAINT ck_chat_messages_token_count CHECK (token_count >= 0),
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE INDEX ix_chat_messages_session_created_at ON chat_messages (session_id, created_at);

CREATE TABLE document_chunks (
	id INTEGER NOT NULL AUTO_INCREMENT,
	document_id INTEGER NOT NULL,
	chunk_index INTEGER NOT NULL,
	content TEXT NOT NULL,
	embedding JSON,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_document_chunks_document_id_chunk_index UNIQUE (document_id, chunk_index),
	CONSTRAINT ck_document_chunks_chunk_index CHECK (chunk_index >= 0),
	CONSTRAINT ck_document_chunks_embedding CHECK (embedding IS NULL OR (JSON_TYPE(embedding) = 'ARRAY' AND JSON_LENGTH(embedding) = 768)),
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE quiz_questions (
	id INTEGER NOT NULL AUTO_INCREMENT,
	quiz_id INTEGER NOT NULL,
	position SMALLINT NOT NULL,
	question_text TEXT NOT NULL,
	options JSON NOT NULL,
	correct_answer CHAR(1) NOT NULL,
	explanation TEXT NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_quiz_questions_quiz_id_position UNIQUE (quiz_id, position),
	CONSTRAINT ck_quiz_questions_position CHECK (position BETWEEN 1 AND 5),
	CONSTRAINT ck_quiz_questions_correct_answer CHECK (correct_answer IN ('A', 'B', 'C', 'D')),
	FOREIGN KEY(quiz_id) REFERENCES quizzes (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

CREATE TABLE quiz_answers (
	id INTEGER NOT NULL AUTO_INCREMENT,
	question_id INTEGER NOT NULL,
	user_answer CHAR(1) NOT NULL,
	is_correct BOOL NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_quiz_answers_question_id UNIQUE (question_id),
	CONSTRAINT ck_quiz_answers_user_answer CHECK (user_answer IN ('A', 'B', 'C', 'D')),
	FOREIGN KEY(question_id) REFERENCES quiz_questions (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_as_cs;

INSERT INTO alembic_version (version_num) VALUES ('0002_integer_ids');
