#!/bin/sh
set -eu

usage() {
    echo "Usage: sh scripts/test.sh [smoke|unit|wallet|integration [group]|test <test names...>]"
}

needs_elastic=false
suite=${1:-smoke}
if [ "$#" -gt 0 ]; then shift; fi
case "$suite" in
    smoke|unit|wallet)
        if [ "$#" -ne 0 ]; then usage >&2; exit 2; fi
        case "$suite" in
            smoke)
                needs_elastic=true
                set -- -v tests.integration.transactions.test_transactions.BasicTransactionTests.test_sending_and_receiving
                ;;
            unit) set -- discover -v tests.unit ;;
            wallet) set -- discover -v tests.unit.wallet ;;
        esac
        ;;
    integration)
        needs_elastic=true
        if [ "$#" -gt 1 ]; then usage >&2; exit 2; fi
        case "${1:-all}" in
            all) set -- discover -v tests.integration ;;
            blockchain|claims|datanetwork|other|takeovers|transactions)
                set -- discover -v "tests.integration.$1"
                ;;
            *) usage >&2; exit 2 ;;
        esac
        ;;
    test)
        needs_elastic=true
        if [ "$#" -eq 0 ]; then usage >&2; exit 2; fi
        set -- -v "$@"
        ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
run_dir=$(mktemp -d)
es_id=
cleanup() {
    for cid_file in "$run_dir/test.cid" "$run_dir/elastic.cid"; do
        if [ -s "$cid_file" ]; then
            docker rm --force "$(cat "$cid_file")" >/dev/null 2>&1 || true
        fi
    done
    rm -f "$run_dir/test.cid" "$run_dir/elastic.cid" "$run_dir/image.id"
    rmdir "$run_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker build --platform linux/amd64 --file "$repo_dir/docker/Dockerfile.test" \
    --iidfile "$run_dir/image.id" "$repo_dir"
sdk_image=$(cat "$run_dir/image.id")
network=none
if [ "$needs_elastic" = true ]; then
    es_image=docker.elastic.co/elasticsearch/elasticsearch:7.12.1@sha256:8e93628cef91f721bc9c4662f4a8f088752c2464fa966665413f175f8a96d268
    es_id=$(docker run --detach --platform linux/amd64 --cidfile "$run_dir/elastic.cid" \
        --network none --memory 2g --cpus 2 \
        --env discovery.type=single-node --env xpack.security.enabled=false \
        --env 'ES_JAVA_OPTS=-Xms512m -Xmx512m' "$es_image")
    attempt=0
    until docker exec "$es_id" curl -fsS --max-time 2 http://127.0.0.1:9200/ >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 60 ] || [ "$(docker inspect --format '{{.State.Running}}' "$es_id")" != true ]; then
            docker logs "$es_id"
            exit 1
        fi
        sleep 1
    done
    network=container:$es_id
fi

# Share only the isolated container's loopback network. No host ports or mounts.
docker run --init --platform linux/amd64 --cidfile "$run_dir/test.cid" \
    --network "$network" --memory 4g --cpus 4 --ulimit nofile=65536:65536 \
    "$sdk_image" timeout --kill-after=10s "${TEST_TIMEOUT:-3600}s" \
    python -m unittest "$@"
