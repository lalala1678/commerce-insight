from decimal import Decimal
import json
import pandas as pd
import pytest
from scripts.audit_data import inspect_csv, money_values, relationship
from scripts.verify_audit import verify

def test_missingness_keeps_zero_and_na_and_does_not_modify_file(tmp_path):
    path=tmp_path/'input.csv'
    payload='review_comment_title,review_score\n,5\n"  ",4\nNA,0\nnull,3\n'
    path.write_text(payload,encoding='utf-8')
    _,info=inspect_csv(path,tmp_path)
    assert info['rows']==4
    assert info['columns'][0]['missing']==2
    assert info['columns'][1]['missing']==0
    assert path.read_text(encoding='utf-8')==payload

def test_non_rectangular_input_is_not_silently_truncated(tmp_path):
    path=tmp_path/'input.csv'
    path.write_text('order_id,price\none,1.00,extra\n',encoding='utf-8')
    with pytest.raises(ValueError,match='Non-rectangular'):inspect_csv(path,tmp_path)

def test_input_outside_declared_root_is_rejected(tmp_path):
    child=tmp_path/'raw';child.mkdir()
    path=tmp_path/'outside.csv';path.write_text('order_id\none\n',encoding='utf-8')
    with pytest.raises(ValueError,match='explicit raw root'):inspect_csv(path,child)

def test_money_is_exact_and_bad_values_are_counted():
    values,invalid,negative=money_values(pd.Series(['0.10','0.20','-1.00','0.001','NaN','']))
    assert int(values.iloc[:2].sum())==30
    assert negative==1
    assert invalid==3

def test_relationship_distinguishes_null_and_unmatched_and_fanout():
    child=pd.DataFrame({'key':['a','a','b','']})
    parent=pd.DataFrame({'key':['a','a']})
    result=relationship(child,'key',parent,'key')
    assert result['missing_child_keys']==1
    assert result['unmatched_child_rows']==1
    assert result['parent_duplicate_key_rows']==1
