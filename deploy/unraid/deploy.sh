#!/usr/bin/env bash
#
# MusicTag Lite — Unraid 部署 / 更新脚本（可复用）
#
# 作用：把本仓库源码同步到 NAS，并注册为 Unraid「Compose Manager」栈后构建启动，
#       使其可以在 Unraid 后台 → Docker → Compose 中直接 启动/停止/更新/编辑/看日志。
#
# 用法（在仓库根目录执行）：
#   deploy/unraid/deploy.sh
#   NAS_HOST=root@10.0.0.5 PORT=8080 MUSIC_PATH=/mnt/user/media/music deploy/unraid/deploy.sh
#
# 可用环境变量（均有默认值）：
#   NAS_HOST    默认 root@192.168.31.252
#   APP_DIR     默认 /mnt/user/appdata/musictag-lite      （源码 src/ 与数据 data/ 的根）
#   STACK_NAME  默认 musictag-lite
#   STACK_DIR   默认 /boot/config/plugins/compose.manager/projects/<STACK_NAME>
#   MUSIC_PATH  默认 /mnt/user/media/媒体/媒体库/音乐
#   PORT        默认 8000
set -euo pipefail

NAS_HOST="${NAS_HOST:-root@192.168.31.252}"
APP_DIR="${APP_DIR:-/mnt/user/appdata/musictag-lite}"
STACK_NAME="${STACK_NAME:-musictag-lite}"
STACK_DIR="${STACK_DIR:-/boot/config/plugins/compose.manager/projects/$STACK_NAME}"
MUSIC_PATH="${MUSIC_PATH:-/mnt/user/media/媒体/媒体库/音乐}"
PORT="${PORT:-8000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

echo "==> 目标"
echo "    NAS      : $NAS_HOST"
echo "    源码     : $APP_DIR/src"
echo "    数据     : $APP_DIR/data"
echo "    栈目录   : $STACK_DIR"
echo "    曲库     : $MUSIC_PATH  ->  /music"
echo "    端口     : $PORT"
echo

# ---------- 1) 同步源码（排除构建产物；禁用 macOS AppleDouble 与扩展属性） ----------
echo "==> 同步源码到 NAS"
# COPYFILE_DISABLE=1 抑制 AppleDouble 的 ._* 侧车文件；
# --no-xattrs 阻止 bsdtar 把扩展属性（com.apple.provenance/macl）写成 pax 头，
# 否则目标端 GNU tar 会打印「Ignoring unknown extended header keyword」。
COPYFILE_DISABLE=1 tar --no-xattrs -czf - \
  --exclude='./.git' \
  --exclude='./frontend/node_modules' \
  --exclude='./backend/.venv' \
  --exclude='./frontend/dist' \
  --exclude='./data' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='./backend/.pytest_cache' \
  --exclude='./backend/.ruff_cache' \
  --exclude='./backend/*.egg-info' \
  --exclude='.DS_Store' --exclude='._*' --exclude='*/._*' \
  -C "$REPO_ROOT" . \
  | ssh "${SSH_OPTS[@]}" "$NAS_HOST" "
      rm -rf '$APP_DIR/src' && mkdir -p '$APP_DIR/src' && tar xzf - -C '$APP_DIR/src' &&
      mkdir -p '$APP_DIR/data' && chmod 777 '$APP_DIR/data' &&
      echo '    源码与数据目录就绪'
    "

# ---------- 2) 注册 Compose Manager 栈（保留已生成的密钥与自定义配置） ----------
echo "==> 配置 Compose Manager 栈"
REMOTE_ENV="$(ssh "${SSH_OPTS[@]}" "$NAS_HOST" "cat '$STACK_DIR/.env' 2>/dev/null || true")"
SECRET="$(printf '%s\n' "$REMOTE_ENV" | sed -n 's/^APP_SECRET_KEY=//p')"
if [ -z "$SECRET" ]; then
  SECRET="$(ssh "${SSH_OPTS[@]}" "$NAS_HOST" 'openssl rand -hex 32')"
fi

# 保留脚本不管理的键（例如手填的 AI_API_KEY / ACOUSTID_API_KEY），避免部署时被覆盖
EXTRA_ENV="$(printf '%s\n' "$REMOTE_ENV" \
  | grep -vE '^(APP_DIR|MUSIC_PATH|PORT|APP_SECRET_KEY)=' \
  | grep -v '^[[:space:]]*$' || true)"
# 也允许通过环境变量直接下发这些可选配置
for KEY in AI_ENABLED AI_BASE_URL AI_MODEL AI_API_KEY ACOUSTID_API_KEY; do
  VALUE="${!KEY:-}"
  if [ -n "$VALUE" ]; then
    EXTRA_ENV="${EXTRA_ENV}${EXTRA_ENV:+$'\n'}${KEY}=${VALUE}"
  fi
done

ssh "${SSH_OPTS[@]}" "$NAS_HOST" "mkdir -p '$STACK_DIR'"
ssh "${SSH_OPTS[@]}" "$NAS_HOST" "cat > '$STACK_DIR/docker-compose.yml'" < "$SCRIPT_DIR/docker-compose.yml"
{
  echo "APP_DIR=$APP_DIR"
  echo "MUSIC_PATH=$MUSIC_PATH"
  echo "PORT=$PORT"
  echo "APP_SECRET_KEY=$SECRET"
  printf '%s\n' "$EXTRA_ENV"
} | ssh "${SSH_OPTS[@]}" "$NAS_HOST" "cat > '$STACK_DIR/.env'"
echo "    已写入 $STACK_DIR/{docker-compose.yml,.env}"

# ---------- 3) 迁移历史数据并清理旧部署 ----------
echo "==> 迁移历史数据 / 清理旧部署"
ssh "${SSH_OPTS[@]}" "$NAS_HOST" "
  # 旧布局的 SQLite 在 \$APP_DIR/docker/data，新布局在 \$APP_DIR/data
  if [ -d '$APP_DIR/docker/data' ] && [ ! -f '$APP_DIR/data/musictag.db' ]; then
    mkdir -p '$APP_DIR/data' && cp -a '$APP_DIR/docker/data/.' '$APP_DIR/data/' &&
    echo '    已迁移旧数据到 $APP_DIR/data'
  fi
  if [ -f '$APP_DIR/docker/docker-compose.yml' ]; then
    (cd '$APP_DIR/docker' && docker compose -p docker down) >/dev/null 2>&1 || true
  fi
  rm -rf '$APP_DIR/docker'
  # 清理早期误落在根目录的源码副本（新布局统一在 \$APP_DIR/src）
  if [ -d '$APP_DIR/src' ]; then
    rm -rf '$APP_DIR/backend' '$APP_DIR/frontend' '$APP_DIR/docs' '$APP_DIR/README.md'
  fi
  docker rm -f '$STACK_NAME' >/dev/null 2>&1 || true
  echo '    已清理'
"

# ---------- 4) 构建并启动（并清理上一次构建留下的孤立镜像） ----------
echo "==> 构建并启动（首次构建约 1-2 分钟；仅当依赖变化时才重新下载 Python 库）"
ssh "${SSH_OPTS[@]}" "$NAS_HOST" "
  OLD_IMAGE=\$(docker images -q '$STACK_NAME:latest' | head -n1)
  # DOCKER_BUILDKIT=1：构建缓存存于 BuildKit 缓存区（而不是悬空镜像），
  # 因此下面的 image prune 不会误删缓存，改源码后只重建变更层、不重新下载依赖。
  cd '$STACK_DIR' && DOCKER_BUILDKIT=1 docker compose up -d --build && docker compose ps

  # 1) 精确清理上一次的同名镜像（重建后它会变成 <none> 悬空镜像）
  NEW_IMAGE=\$(docker images -q '$STACK_NAME:latest' | head -n1)
  if [ -n \"\$OLD_IMAGE\" ] && [ \"\$OLD_IMAGE\" != \"\$NEW_IMAGE\" ]; then
    docker rmi \"\$OLD_IMAGE\" >/dev/null 2>&1 && echo \"    已移除旧镜像 \${OLD_IMAGE:0:12}\"
  fi

  # 2) 只清理 24 小时前的孤立镜像，避免误删近期构建缓存
  DANGLING=\$(docker images -q --filter dangling=true --filter until=24h | wc -l | tr -d ' ')
  if [ \"\$DANGLING\" != \"0\" ]; then
    docker image prune -f --filter until=24h >/dev/null 2>&1 && echo \"    已清理 \$DANGLING 个陈旧孤立镜像\"
  fi

  echo '    当前镜像:'
  docker images '$STACK_NAME' --format '      {{.Repository}}:{{.Tag}}  {{.ID}}  {{.Size}}  {{.CreatedSince}}'
"

# ---------- 5) 健康检查（探测失败不影响部署结果判定） ----------
echo "==> 等待健康检查"
ssh "${SSH_OPTS[@]}" "$NAS_HOST" "
  for i in \$(seq 1 60); do
    if curl -fsS http://127.0.0.1:$PORT/api/health >/tmp/mtl-health.json 2>/dev/null; then break; fi
    sleep 1
  done
  cat /tmp/mtl-health.json 2>/dev/null; echo
" || true

IP="${NAS_HOST#*@}"
echo
echo "✅ 部署完成"
echo "   访问    : http://${IP}:${PORT}"
echo "   管理    : Unraid → Docker → Compose → 栈「${STACK_NAME}」（启动/停止/更新/编辑/日志）"
echo "   更新    : 再次执行本脚本即可重建"
