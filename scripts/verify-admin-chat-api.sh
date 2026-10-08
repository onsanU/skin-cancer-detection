#!/usr/bin/env bash
# 后端接口验证：看板 chat 字段 + 趋势 grain/source 组合 + 问答记录 CRUD
set -uo pipefail
BASE="http://127.0.0.1:8000"

TOKEN=$(curl -s -m 15 -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<密码>"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('token') or d.get('access_token',''))")
[ -z "$TOKEN" ] && { echo "✘ 登录失败，拿不到 token"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"
echo "✔ 登录成功"

echo
echo "=== 1. stats 的 chat 字段 ==="
curl -s -m 20 "$BASE/admin/api/stats" -H "$AUTH" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d.get('chat') or {}
print('  图像:  total_records=%s  恶性=%s  良性=%s  占比=%s%%' % (d['total_records'], d['malignant'], d['benign'], d['malignant_rate']))
print('  问答:  会话=%s  消息=%s  提问=%s  今日新会话=%s  平均回答=%sms' % (c.get('sessions'), c.get('messages'), c.get('questions'), c.get('today_sessions'), c.get('avg_reply_ms')))
print('  问答Top:', [(u['username'], u['count']) for u in (c.get('top_users') or [])][:5])
assert c, '缺 chat 字段'
assert d['malignant'] + d['benign'] == d['total_records'], '良恶性之和 != 总记录数'
assert d['total_records'] == 1442 or d['total_records'] > 0
print('  ✔ chat 字段完整，良恶性口径仍为纯图像')
"

echo
echo "=== 2. 趋势 grain × source 九种组合 ==="
for g in day week month; do
  for s in record chat all; do
    curl -s -m 20 "$BASE/admin/api/stats?grain=$g&source=$s" -H "$AUTH" \
      | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = d['trend']
assert d['trend_grain'] == '$g' and d['trend_source'] == '$s', '参数回显错'
total = sum(x['count'] for x in t)
pts = ', '.join('%s:%s' % (x['date'], x['count']) for x in t[-3:])
print('  %-5s / %-6s → %2d 点, 合计 %5d  (%s)' % ('$g', '$s', len(t), total, pts))
"
  done
done

echo
echo "=== 3. 问答记录列表 ==="
curl -s -m 20 "$BASE/admin/api/chats?limit=5" -H "$AUTH" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  total=%s  limit=%s  返回=%s 条' % (d['total'], d['limit'], len(d['items'])))
for it in d['items']:
    print('   #%s %-10s %-24s 消息%s' % (it['id'], it['username'], it['title'][:22], it['msg_count']))
assert d['total'] >= 1, '应有问答数据'
print('  ✔ 列表可用')
"

echo
echo "=== 4. 问答详情（含消息）==="
curl -s -m 20 "$BASE/admin/api/chats/4" -H "$AUTH" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  会话#%s「%s」by %s，%s 条消息' % (d['id'], d['title'], d['username'], len(d['messages'])))
for m in d['messages'][:4]:
    print('    [%-9s] %s%s' % (m['role'], (m['content'] or '')[:48].replace(chr(10),' '), ' 📷' if m['has_image'] else ''))
assert d['messages'], '消息为空'
print('  ✔ 详情可用')
"

echo
echo "=== 5. 不存在的会话（应返回 deleted:0 而非误报成功）==="
curl -s -m 20 -X DELETE "$BASE/admin/api/chats/999999" -H "$AUTH"; echo

echo
echo "=== 6. 非管理员访问（应 403/401）==="
curl -s -o /dev/null -w "  无 token → HTTP %{http_code}\n" -m 15 "$BASE/admin/api/chats"
curl -s -o /dev/null -w "  假 token → HTTP %{http_code}\n" -m 15 "$BASE/admin/api/chats" -H "Authorization: Bearer fake.token.here"
