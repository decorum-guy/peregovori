"""Urgent demo sequencer. Requires armed on-VM watchdog; no VM start."""
import json, subprocess, sys, time
from pathlib import Path
from training.runtime_v2.common import ROOT

def call(*args):
    subprocess.run(list(args), check=True, cwd=ROOT)

def left():
    info=json.loads((ROOT/"training/outputs/intelion_deadline.json").read_text())
    if info["server_id"] != 11425:
        raise RuntimeError("Wrong Intelion server")
    return int((info["deadline_epoch"]-time.time())/60)

def main():
    out=ROOT/"training/outputs/runtime_v2"
    out.mkdir(parents=True,exist_ok=True)
    call(sys.executable,"training/upload_private_release.py","check")
    corpus="training/derived/runtime_v2/accepted180_verified"
    token="training/derived/runtime_v2/tokenizers/8B"
    for name,minimum in [("qwen3_8b_r16_e1",90),("qwen3_8b_r16_e2",155),("qwen3_8b_r32_e2",180)]:
        print("TIME",left(),"minutes; proposed",name,flush=True)
        if left()<minimum:
            print("SKIP",name,flush=True)
            continue
        cfg="training/runtime_v2/configs/"+name+".json"
        base=out/name
        if base.exists() or (out/(name+"_preflight")).exists():
            raise RuntimeError("Existing output: refusing overwrite "+name)
        cmd=[sys.executable,"-m","training.runtime_v2.demo_budget_entry"]
        opts=["--config",cfg,"--corpus",corpus,"--tokenizer-local",token,
              "--budget","training/outputs/intelion_deadline.json","--execute"]
        call(*(cmd+["preflight"]+opts))
        call(*(cmd+["train"]+opts+["--preflight-report",str(out/(name+"_preflight")/"preflight.json")]))
        call(sys.executable,"-m","training.runtime_v2.check_adapter","--output",str(base))
        target=out/"demo_backups"
        target.mkdir(exist_ok=True)
        archive=target/(name+"_adapter.tar.gz")
        call("tar","-czf",str(archive),"-C",str(base),
             "adapter","status.json","identity.json","tokenization.json","SHA256.json")
        with open(str(archive)+".sha256","w") as f:
            subprocess.run(["sha256sum",str(archive)],check=True,stdout=f,cwd=ROOT)
        call(sys.executable,"training/upload_private_release.py","upload",
             "--tag","train-v2-"+name+"-20261015","--file",str(archive),
             "--file",str(archive)+".sha256")
        print("UPLOADED",name,flush=True)

if __name__=="__main__":
    main()
