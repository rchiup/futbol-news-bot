"""Bounded nightly warmup from named entities in the newsroom queue."""
import json
import time
from pathlib import Path
import requests
from photo_bank import entities, load_bank, save_bank, find_entity_photo
from portraits import normalize

def main():
    queue=json.loads(Path("data/queue.json").read_text())
    bank=load_bank()
    attempted=0
    for item in reversed(queue):
        groups=entities(item,item.get("visual_entities") or item)
        for kind,names in (("person",groups["personas"]),("club",groups["clubes"])):
            for name in names:
                key=kind+":"+normalize(name)
                if key in bank:
                    continue
                if attempted>=30:
                    return
                attempted+=1
                try:
                    photo=find_entity_photo(name,kind)
                    if photo:
                        bank[key]=photo
                        save_bank(bank)
                except (requests.RequestException,ValueError,KeyError,TypeError):
                    pass
                time.sleep(1)

if __name__=="__main__":
    main()
