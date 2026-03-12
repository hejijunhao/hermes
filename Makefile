.PHONY: up down deploy logs ssh status

# Docker local
up:
	docker compose -f gateway/docker-compose.yml up --build

down:
	docker compose -f gateway/docker-compose.yml down

# Fly.io
deploy:
	fly deploy --config gateway/fly.toml

logs:
	fly logs --config gateway/fly.toml

ssh:
	fly ssh console --config gateway/fly.toml

status:
	fly status --config gateway/fly.toml
