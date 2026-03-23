backend-install:
	cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt

backend-migrate:
	cd backend && source venv/bin/activate && python manage.py migrate

backend-bootstrap:
	cd backend && source venv/bin/activate && python manage.py bootstrap_kuboard

backend-dev:
	cd backend && source venv/bin/activate && python manage.py runserver

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

redis-up:
	docker compose up -d redis

redis-down:
	docker compose down

release-check:
	sh ./scripts/release_check.sh

prod-config:
	docker compose -f docker-compose.prod.yml config

prod-up:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down

sqlite-backup:
	python ./scripts/sqlite_backup.py

sqlite-restore:
	@test -n "$(BACKUP)" || (echo "Usage: make sqlite-restore BACKUP=./backups/file.sqlite3 [TARGET=backend/db.sqlite3] [FORCE=1]"; exit 1)
	python ./scripts/sqlite_restore.py "$(BACKUP)" "$(if $(TARGET),$(TARGET),backend/db.sqlite3)" $(if $(FORCE),--force,)

helm-lint:
	helm lint deploy/helm/kuboard

helm-template:
	helm template kuboard deploy/helm/kuboard

helm-package:
	mkdir -p dist/helm
	helm package deploy/helm/kuboard --destination dist/helm
