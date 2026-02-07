import argparse
import json
import os
from docx import Document

def parse_args():
	parser = argparse.ArgumentParser(description="JSONからDOCXを生成")
	parser.add_argument('-i', '--input', default='C:\\Users\\ikbas\\Downloads\\signate\\financial-report\\app\\json-to-docx\\example_filled.json', help='入力JSONファイル')
	parser.add_argument('-o', '--output', default='C:\\Users\\ikbas\\Downloads\\signate\\financial-report\\app\\json-to-docx\\output.docx', help='出力DOCXファイル')
	return parser.parse_args()

def add_section(doc, section, level=1):
	doc.add_heading(section.get('title', ''), level=level)
	if 'content' in section:
		content = section['content']
		# 辞書型データを文章化
		def dict_to_sentence(d):
			sentence = ""
			# イニシアティブ用
			if 'name' in d or 'description' in d:
				if d.get('name'):
					sentence += f"『{d.get('name')}』: "
				if d.get('description'):
					sentence += f"{d.get('description')}"
				if d.get('linked_issue'):
					sentence += f"（課題: {d.get('linked_issue')}）"
				if d.get('execution_requirements'):
					req = d['execution_requirements']
					req_text = []
					if req.get('people'): req_text.append(f"人材: {req['people']}")
					if req.get('money'): req_text.append(f"資金: {req['money']}")
					if req.get('time'): req_text.append(f"期間: {req['time']}")
					if req_text:
						sentence += f"（必要リソース: {', '.join(req_text)}）"
				if d.get('kpi'):
					sentence += f"（KPI: {', '.join(d['kpi'])}）"
				if d.get('expected_effect'):
					sentence += f" 期待効果: {d['expected_effect']}"
				if d.get('risks_and_mitigations'):
					sentence += f" リスク対応: {d['risks_and_mitigations']}"
				return sentence
			# その他辞書型データ
			for k, v in d.items():
				if isinstance(v, list):
					sentence += " " + "、".join([str(x) for x in v])
				elif isinstance(v, dict):
					sentence += " " + dict_to_sentence(v)
				elif v:
					sentence += f" {v}"
			return sentence.strip()

		if isinstance(content, dict):
			for k, v in content.items():
				if isinstance(v, list):
					for item in v:
						if isinstance(item, dict):
							doc.add_paragraph(dict_to_sentence(item), style='ListBullet')
						else:
							doc.add_paragraph(str(item), style='ListBullet')
				elif isinstance(v, dict):
					doc.add_paragraph(dict_to_sentence(v))
				elif v:
					doc.add_paragraph(str(v))
		elif isinstance(content, list):
			for item in content:
				if isinstance(item, dict):
					doc.add_paragraph(dict_to_sentence(item), style='ListBullet')
				else:
					doc.add_paragraph(str(item), style='ListBullet')
		elif content:
			doc.add_paragraph(str(content))
	if 'subsections' in section:
		for subsection in section['subsections']:
			add_section(doc, subsection, level=level+1)

def main():
	args = parse_args()
	input_path = args.input
	output_path = args.output

	if not os.path.exists(input_path):
		print(f"入力ファイルが見つかりません: {input_path}")
		return

	with open(input_path, 'r', encoding='utf-8') as f:
		data = json.load(f)

	doc = Document()

	meta = data.get('meta', {})
	title = meta.get('title', '報告書')
	doc.add_heading(title, 0)
	if meta:
		doc.add_paragraph(f"企業コード: {meta.get('company_code', '')}")
		doc.add_paragraph(f"最大文字数: {meta.get('max_characters', '')}")
		doc.add_paragraph(f"言語: {meta.get('language', '')}")

	sections = data.get('sections', [])
	for section in sections:
		add_section(doc, section, level=1)

	doc.save(output_path)
	print(f"DOCXファイルを生成しました: {output_path}")

if __name__ == '__main__':
	main()
