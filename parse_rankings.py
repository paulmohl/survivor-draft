import json, re

TOP72 = [
    (1,"Jahmyr Gibbs","DET","RB"),
    (2,"Ja'Marr Chase","CIN","WR"),
    (3,"Puka Nacua","LAR","WR"),
    (4,"Bijan Robinson","ATL","RB"),
    (5,"Amon-Ra St. Brown","DET","WR"),
    (6,"Jaxon Smith-Njigba","SEA","WR"),
    (7,"Jonathan Taylor","IND","RB"),
    (8,"Christian McCaffrey","SF","RB"),
    (9,"CeeDee Lamb","DAL","WR"),
    (10,"Justin Jefferson","MIN","WR"),
    (11,"James Cook","BUF","RB"),
    (12,"Kenneth Walker III","KC","RB"),
    (13,"Saquon Barkley","PHI","RB"),
    (14,"Nico Collins","HOU","WR"),
    (15,"Brock Bowers","LV","TE"),
    (16,"Drake London","ATL","WR"),
    (17,"Chase Brown","CIN","RB"),
    (18,"De'Von Achane","MIA","RB"),
    (19,"Chris Olave","NO","WR"),
    (20,"George Pickens","DAL","WR"),
    (21,"Omarion Hampton","LAC","RB"),
    (22,"A.J. Brown","NE","WR"),
    (23,"DeVonta Smith","PHI","WR"),
    (24,"Malik Nabers","NYG","WR"),
    (25,"Trey McBride","ARI","TE"),
    (26,"Derrick Henry","BAL","RB"),
    (27,"Ashton Jeanty","LV","RB"),
    (28,"Zay Flowers","BAL","WR"),
    (29,"Jaylen Waddle","DEN","WR"),
    (30,"Tee Higgins","CIN","WR"),
    (31,"Josh Allen","BUF","QB"),
    (32,"Garrett Wilson","NYJ","WR"),
    (33,"Jordan Love","ARI","RB"),
    (34,"Cole Loveland","CHI","TE"),
    (35,"Breece Hall","NYJ","RB"),
    (36,"Rashee Rice","KC","WR"),
    (37,"Ladd McConkey","LAC","WR"),
    (38,"Tetairoa McMillan","CAR","WR"),
    (39,"Kyren Williams","LAR","RB"),
    (40,"Javonte Williams","DAL","RB"),
    (41,"Travis Etienne Jr.","NO","RB"),
    (42,"Emeka Egbuka","TB","WR"),
    (43,"Luther Burden III","CHI","WR"),
    (44,"Lamar Jackson","BAL","QB"),
    (45,"D'Andre Swift","CHI","RB"),
    (46,"DJ Moore","BUF","WR"),
    (47,"Terry McLaurin","WAS","WR"),
    (48,"Jameson Williams","DET","WR"),
    (49,"Parfait Washington","JAC","WR"),
    (50,"Tucker Warren","IND","TE"),
    (51,"Cam Skattebo","NYG","RB"),
    (52,"Rome Odunze","CHI","WR"),
    (53,"Davante Adams","LAR","WR"),
    (54,"Christian Watson","GB","WR"),
    (55,"Bucky Irving","TB","RB"),
    (56,"Joe Burrow","CIN","QB"),
    (57,"David Montgomery","HOU","RB"),
    (58,"Bhayshul Tuten","JAC","RB"),
    (59,"Drake Maye","NE","QB"),
    (60,"Quinshon Judkins","CLE","RB"),
    (61,"Mike Evans","SF","WR"),
    (62,"Johnathan Price","SEA","RB"),
    (63,"Marvin Harrison Jr.","ARI","WR"),
    (64,"Rhamondre Stevenson","NE","RB"),
    (65,"Jalen Hurts","PHI","QB"),
    (66,"Jayden Daniels","WAS","QB"),
    (67,"Caleb Williams","CHI","QB"),
    (68,"Tony Henderson","NE","RB"),
    (69,"Tucker Kraft","GB","TE"),
    (70,"Sam LaPorta","DET","TE"),
    (71,"Brian Thomas Jr.","JAC","WR"),
    (72,"Jaylen Warren","PIT","RB"),
]

# Bye weeks 2026 (approximate/best-known)
BYE = {
    "ARI":5,"ATL":11,"BAL":14,"BUF":7,"CAR":9,"CHI":7,
    "CIN":6,"CLE":10,"DAL":7,"DEN":14,"DET":5,"GB":6,
    "HOU":10,"IND":14,"JAC":9,"KC":6,"LAC":5,"LAR":9,
    "LV":10,"MIA":11,"MIN":6,"NE":7,"NO":11,"NYG":11,
    "NYJ":12,"PHI":5,"PIT":9,"SEA":5,"SF":8,"TB":11,
    "TEN":10,"WAS":14,"FA":0,
}

players = []
for rank, name, team, pos in TOP72:
    players.append({"rank": rank, "name": name, "team": team, "pos": pos,
                    "bye": BYE.get(team, 0), "adp": rank})

# Parse rankings_raw.txt — stored as a JSON-encoded string
raw = open("rankings_raw.txt").read().strip()
# Strip outer quotes if present
if raw.startswith('"') and raw.endswith('"'):
    raw = json.loads(raw)
# Now decode escape sequences
text = raw.replace('\\n', '\n').replace('\\t', '\t')

seen = {p["rank"] for p in players}
NFL_POS = {'QB','RB','WR','TE','K','DST','D/ST','K'}
NFL_TEAMS = {
    'ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET',
    'GB','HOU','IND','JAC','KC','LAC','LAR','LV','MIA','MIN','NE','NO',
    'NYG','NYJ','PHI','PIT','SEA','SF','TB','TEN','WAS','FA',
}

# Pattern for regular players: rank\t\n name \n TEAM \n POS
reg_pattern = re.compile(
    r'(\d+)\t+\n([^\n]+)\n([A-Z]{2,4})\n(QB|RB|WR|TE|K)',
    re.MULTILINE
)
# Pattern for DST: rank\t\n TEAM \n DST
dst_pattern = re.compile(
    r'(\d+)\t+\n([A-Z]{2,4})\n(DST|D/ST)\n',
    re.MULTILINE
)

for m in reg_pattern.finditer(text):
    rank = int(m.group(1))
    name = m.group(2).strip()
    team = m.group(3).strip()
    pos = m.group(4).strip()
    if rank not in seen and rank <= 378 and team in NFL_TEAMS:
        players.append({"rank": rank, "name": name, "team": team, "pos": pos,
                        "bye": BYE.get(team, 0), "adp": rank})
        seen.add(rank)

for m in dst_pattern.finditer(text):
    rank = int(m.group(1))
    team = m.group(2).strip()
    pos = 'DST'
    if rank not in seen and rank <= 378 and team in NFL_TEAMS:
        players.append({"rank": rank, "name": f"{team} DST", "team": team, "pos": pos,
                        "bye": BYE.get(team, 0), "adp": rank})
        seen.add(rank)

players.sort(key=lambda x: x["rank"])
print(f"Parsed {len(players)} players")
for p in players[:5]:
    print(p)

with open("players.json", "w") as f:
    json.dump(players, f, indent=2)
print("Saved players.json")
