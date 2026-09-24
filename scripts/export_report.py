"""Generate a reproducible local historical report, without an LLM or scheduler."""
import argparse
import json
from pathlib import Path
from backend.db import make_engine
from backend.reports import build_report, markdown, html_report


def export(start, end, category='', state='', output='reports'):
    db=make_engine()
    try:report=build_report(db,start,end,category,state)
    finally:db.dispose()
    directory=Path(output);directory.mkdir(parents=True,exist_ok=True)
    stem=f'commerce-report-{start}-{end}'
    for ext,content in [('json',json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)),
                        ('md',markdown(report)),('html',html_report(report))]:
        (directory/(stem+'.'+ext)).write_text(content+'\n',encoding='utf-8')
    print(json.dumps({'report':stem,'data_version':report['meta']['data_version'],'files':3}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',default='2018-07-23')
    parser.add_argument('--end',default='2018-07-29')
    parser.add_argument('--category',default='')
    parser.add_argument('--state',default='')
    parser.add_argument('--output',default='reports')
    args=parser.parse_args();export(**vars(args))
