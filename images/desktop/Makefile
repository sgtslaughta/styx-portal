.PHONY: build run stop clean

IMAGE_NAME := selkies-desktop
TAG := latest

build:
	docker build -t $(IMAGE_NAME):$(TAG) .

run: build
	docker compose up -d

stop:
	docker compose down

clean:
	docker compose down -v
	docker rmi $(IMAGE_NAME):$(TAG) 2>/dev/null || true

logs:
	docker compose logs -f

shell:
	docker exec -it selkies-desktop /bin/zsh
