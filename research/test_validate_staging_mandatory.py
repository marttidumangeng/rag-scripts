from validate_staging import validate_robot

base = {
    'name': 'Test',
    'company_name': 'Test Co',
    'description': 'Valid description',
    'purpose': '',
    'features': '',
    'tags': '',
    'industry_keys': '',
    'industries_other': '',
    'use_keys': '',
    'uses_other': '',
    'category_slugs': '',
    'sub_category_slug': '',
    'sources': [{'url': 'https://example.com'}],
    'source_locale': 'en',
}
result = validate_robot(base)
print([(issue.level, issue.field, issue.message) for issue in result.issues])
assert not result.ok
fields = {issue.field for issue in result.issues}
for expected in ('purpose', 'features', 'tags', 'industries', 'uses', 'category_slugs'):
    assert expected in fields, expected

error_case = dict(base)
error_case.update({
    'purpose': 'Valid task purpose',
    'features': 'Valid features',
    'tags': 'robot|automation',
    'industry_keys': 'automotive',
    'use_keys': 'material_handling',
    'category_slugs': 'industrial-robot',
    'description': '502 Bad Gateway Browser Working Host Error',
})
error_result = validate_robot(error_case)
assert any(issue.field == 'description' and issue.level == 'error' for issue in error_result.issues)

cjk_case = dict(error_case)
cjk_case['description'] = '这是中文内容'
cjk_result = validate_robot(cjk_case)
assert any(issue.field == 'description' and issue.level == 'error' for issue in cjk_result.issues)
print('VALIDATOR_CHECK=PASS')
