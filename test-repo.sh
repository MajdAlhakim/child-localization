# Run this in the root of your cloned repo
echo "=== STRUCTURE ===" && find . -not -path './.git/*' -not -path './node_modules/*' | sort

echo ""
echo "=== tasks.json ===" && cat tasks.json

echo ""
echo "=== progress.txt ===" && cat progress.txt

echo ""
echo "=== PERSON-A FILES ===" && \
  for f in backend/app/db/models.py backend/app/db/session.py backend/app/db/init_db.py \
            backend/app/core/config.py backend/app/core/security.py \
            backend/app/api/admin.py backend/app/fusion/offset_corrector.py \
            backend/requirements.txt docker-compose.yml; do
    echo "--- $f ---"
    cat "$f" 2>/dev/null || echo "[MISSING]"
    echo ""
  done

echo ""
echo "=== GIT LOG ===" && git log --oneline -15