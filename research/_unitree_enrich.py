"""One-off enrichment for Unitree Robotics (company 109) To-Review robots.
Fills required taxonomy/tags, replaces Chinese descriptions with English,
adds grounded release years. Uses the admin update-data PATCH endpoint
(M2M set by ID, categories/tags by name). Photos handled separately.
"""
import sys, json
from api_client import ResearchApiClient

c = ResearchApiClient()

# --- taxonomy IDs (resolved from prod) ---
U = {  # uses key -> id
    'manipulation':45,'assembly':21,'research':19,'inspection':7,'exploration':18,
    'transport':16,'other':20,'picking':11,'monitoring':9,'patrol':10,'handling':46,
    'data-collection':71,'general-automation':33,
}
I = {  # industry key -> id
    'research':18,'manufacturing':12,'education':7,'security':16,'defence':19,
    'homes':9,'others':1,'consumer':20,'healthcare':8,'logistics':11,
}
MV = {'legged':12,'wheeled':4,'bipedal':2,'quadruped':3,'humanoid':5,'stationary':10}

# English descriptions (translations of existing zh-CN content + verified facts)
DESC = {
 42: "The Unitree Go2 is a quadrupedal mobile robot from Unitree Robotics, designed for all-terrain dynamic navigation and advanced perception. It is used mainly for autonomous inspection, patrol, and navigation tasks in complex outdoor and industrial environments, supported by 4D LiDAR and AI-assisted control.",
 44: "The Unitree B2 is a large industrial quadruped robot from Unitree Robotics, built to traverse rugged terrain and carry heavy payloads with stability. Its high load capacity and long endurance make it well suited to inspection, defense, and on-site monitoring in demanding environments.",
 126: "The Unitree G1 is a compact humanoid robot from Unitree Robotics, marking the company's expansion from quadrupeds to affordable, human-scale platforms. Built for flexible, dynamic motion and AI-driven interaction, it targets research, education, and companion or social-interaction scenarios rather than heavy industrial work.",
 282: "Laikago is an early-generation commercial quadruped robot from Unitree Robotics and one of the company's first steps toward commercializing affordable legged platforms. First unveiled in 2017, it emphasized electric actuation, a modular joint system, and accessibility for robotics research and development.",
 348: "The Unitree H2 is a new-generation, full-size humanoid robot from Unitree Robotics, reflecting the company's push toward affordable, high-performance general-purpose humanoids. Introduced in 2025, it advances earlier Unitree platforms with improved motion control, higher torque output, stronger onboard AI computing, and a scalable, developer-friendly design.",
 601: "The Unitree GD01 is a large, pilotable transformable mecha from Unitree Robotics, billed as the world's first mass-produced manned mecha. A human operator rides inside the machine, which switches between bipedal and quadrupedal modes; it is built around a titanium-alloy and aerospace-aluminum frame with a carbon-fiber shell for dynamic locomotion and heavy-load mobility.",
 40: "The Unitree H1 is Unitree Robotics' first-generation full-size humanoid robot, showcasing the company's expertise in embodied AI and legged locomotion through agile, dynamic movement. Unveiled in 2023, the H1 focuses on high-speed, robust bipedal motion for applications that require agile navigation of structured, human-centric environments.",
}

# Per-robot patch payloads. Only gap fields included.
PATCH = {
 # --- Chinese descriptions -> English (+ release year) ---
 42:  {'description':DESC[42], 'source_locale':'en', 'release_year':2023},
 44:  {'description':DESC[44], 'source_locale':'en', 'release_year':2023},
 126: {'description':DESC[126],'source_locale':'en', 'release_year':2024},
 282: {'description':DESC[282],'source_locale':'en', 'release_year':2017},
 348: {'description':DESC[348],'source_locale':'en', 'release_year':2025},
 40:  {'description':DESC[40], 'source_locale':'en', 'release_year':2023,
       'categories':['Humanoid'], 'movement_types':[MV['humanoid'],MV['bipedal']]},
 # 601 already has category/uses/industries (non-empty) — only fix the Chinese
 # description + year; leave curated taxonomy untouched. (Duplicate of 660.)
 601: {'description':DESC[601],'source_locale':'en', 'release_year':2026},

 # --- missing category/uses/industry (must) ---
 5305:{'categories':['Robotic-Arms'], 'movement_types':[MV['stationary']],
       'uses':[U['manipulation'],U['assembly'],U['research']],
       'industries':[I['research'],I['manufacturing']], 'release_year':2025},
 5276:{'categories':['Robotic-Arms'], 'movement_types':[MV['stationary']],
       'uses':[U['manipulation'],U['assembly'],U['research']],
       'industries':[I['research'],I['manufacturing']], 'release_year':2025},
 644: {'categories':['Quadruped'], 'movement_types':[MV['legged'],MV['wheeled']],
       'uses':[U['inspection'],U['research'],U['exploration']],
       'industries':[I['research'],I['manufacturing']], 'release_year':2024},
 660: {'categories':['Humanoid'], 'movement_types':[MV['bipedal'],MV['quadruped']],
       'uses':[U['transport'],U['exploration'],U['other']],
       'industries':[I['research'],I['others']], 'release_year':2026},

 # --- missing tags (must) + release year (images handled separately) ---
 4321:{'tags':['Unitree','Unitree Robotics','Humanoid','Bipedal','Compact','Education','Research','Robotics Research'], 'release_year':2025},
 4320:{'tags':['Unitree','Unitree Robotics','Humanoid','Bipedal','Compact','Research','Robotics Research'], 'release_year':2025},
 4319:{'tags':['Unitree','Unitree Robotics','Humanoid','Bipedal','Research','Industrial'], 'release_year':2024},
 4316:{'tags':['Unitree','Unitree Robotics','Humanoid','Bipedal','Compact','Education','Research'], 'release_year':2024},
 4314:{'tags':['Unitree','Unitree Robotics','Quadruped','Legged','Inspection','Industrial','Autonomous'], 'release_year':2025},
 4315:{'tags':['Unitree','Unitree Robotics','Quadruped','Legged','Inspection','Industrial','Autonomous'], 'release_year':2025},
 4317:{'tags':['Unitree','Unitree Robotics','Quadruped','Legged','Mobility','Autonomous'], 'release_year':2023},
 4318:{'tags':['Unitree','Unitree Robotics','Quadruped','Legged','Mobility','Autonomous'], 'release_year':2023},
}

def apply_one(rid, payload):
    resp = c._patch(f'robots/robots/{rid}/update-data/', payload)
    r = resp.get('robot', {})
    return r

if __name__ == '__main__':
    apply = '--apply' in sys.argv
    only = [int(a) for a in sys.argv[1:] if a.isdigit()]
    ids = only or list(PATCH.keys())
    for rid in ids:
        p = PATCH[rid]
        print(f'=== {rid} fields={list(p.keys())}')
        if apply:
            r = apply_one(rid, p)
            print('   ->', {k:(len(v) if isinstance(v,(list,str)) else v) for k,v in {
                'desc':r.get('description'),'locale':r.get('source_locale'),
                'year':r.get('release_year'),'cats':r.get('categories'),
                'uses':[u.get('key') for u in r.get('uses',[])] if r.get('uses') else [],
                'inds':[i.get('key') for i in r.get('industries',[])] if r.get('industries') else [],
                'tags':r.get('tags'),
            }.items()})
    print('APPLIED' if apply else 'DRY RUN (no --apply)')
