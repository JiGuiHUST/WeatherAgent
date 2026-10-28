"""Apply source-backed opening-hours corrections checked on 2026-10-28."""
import json
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"data/wuhan/spots.json"
data=json.loads(p.read_text(encoding="utf8"))
updates={
"huanghelou":dict(days="Mon-Sun",open="08:00",close="17:00",last_entry="16:00",source="https://www.wuchang.gov.cn/zwgk_37/fdzdgknr/shgysy/ly/202209/t20220930_2050896.html",reservation="须自行通过官方渠道购票并确认入园时段；未纳入独立夜游场次",text="官方常规日场：4–10月 08:00–18:00，11–3月 08:00–17:00；规划保守采用 17:00 前离园、16:00 前入场，临时公告优先"),
"hubei_museum":dict(days="Tue-Sun",open="09:00",close="17:00",last_entry="16:00",source="https://hbsbwg.cjyun.org/p/12728.html",reservation="须在官方渠道预约并按预约时段入场；本系统不查询余票、不代预约",text="周二至周日 09:00–17:00，16:00 停止入馆；周一闭馆（节假日与特殊安排以官方公告为准）"),
"wuhan_museum":dict(days="Wed-Mon",open="09:00",close="17:00",last_entry="16:30",source="https://www.jianghan.gov.cn/zfxxgk/fdzdgknr/gysyjs/ggwhfw/gyxwhtyhd/202304/t20230427_2192804.shtml",reservation="出发前通过武汉博物馆官方渠道确认预约与临时公告",text="周三至周一 09:00–17:00，16:30 停止入馆；周二闭馆（法定节假日除外）"),
"qingchuange":dict(days="Tue-Sun",open="09:00",close="17:00",last_entry="16:30",source="https://www.wuhan.gov.cn/zjwh/whly/202603/t20260310_2737818.shtml",reservation="日间免费，须通过官方微信公众号预约；夜间收费场次未纳入自动规划",text="日间周二至周日 09:00–17:00，16:30 停止入馆；周一闭馆（节假日除外）"),
"xinhai_museum":dict(days="Tue-Sun",open="09:00",close="17:00",last_entry="16:00",source="https://1911museum.cn/index/home.html",reservation="按南区安排；北区闭馆日不同，预约及临时调整以官方渠道为准",text="南区：周二至周日 09:00–17:00，16:00 停止入馆；周一闭馆（节假日除外）"),
"wuhan_sci_museum":dict(days="Wed-Sun",open="09:00",close="16:30",last_entry="15:30",source="https://www.whstm.org.cn/shownews/detail/141",reservation="通过武汉科学技术馆官方渠道预约，工作日/节假日场次以预约页面为准",text="常规周三至周日 09:00–16:30，周一、周二闭馆；采用保守 15:30 最晚入场约束，出发前核实预约时段"),
}
for spot in data["spots"]:
    u=updates.get(spot["id"])
    if not u: continue
    oh=spot["open_hours"]
    oh.update(text=u["text"],periods=[{k:u[k] for k in ("days","open","close","last_entry")}],
              source=u["source"],checked="2026-10-28",confidence="高（官方常规开放信息，临时公告优先）",reservation=u["reservation"])
    oh.pop("conflict",None)
data["meta"]["updated"]="2026-10-28"
p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
print("Updated 6 source-backed opening schedules; no ticket availability assumed.")
