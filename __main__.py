# Lead_By_Article
# author: David Mullen
#
#
# @param _SF_INSTANCE - string "dev" or "prod" to choose Salesforce configuration. Actual values are in lead_by_article() function below
# @param _DISC_BASE_URL - Base endpoint for discovery
# @param _COLLECTION_ID - ID of the Discovery Collection containing article information
# @param _DISC_USER - Discovery API User Name (apikey)
# @param _DISC_PASS - Discovery API Password  (apikey value)
#
import sys
import requests
import json
import re
import time
import smtplib, ssl
import os
from datetime import timezone, datetime
import fpdf
from fpdf import FPDF
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
fpdf.set_global("SYSTEM_TTFONTS", os.path.join(os.path.dirname(__file__),'fonts'))



# @DEV: Queries discovery by article ID and generate leads per company entity found in the article
# @PARAM: _article_id is the string id article you wish to target.
# @RET: Returns a dict containing the success/failure of the lead generation
def lead_by_article(inputs):
	# define SF static values based on the instance flag
	if inputs["SF_INSTANCE"] == "dev":
		RF_URL = "https://test.salesforce.com/services/oauth2/token"
		SF_URL = "https://wrightsmedia--wrightsdev.my.salesforce.com/services/data/"
		RF_KEY = "3MVG93MGy9V8hF9P5tOvZXvSk6YdouzlN5M2wsFr82GfKPFAZK9G0v4Kt7WEyik2lLeW46_KwAhnK1NrUgSn4"
		RF_SECRET = "3C0FFEE636183C52084EF72BCB823FEDE84BE5E8323AF9DFBEDA6F459AAB08E1"
		RF_TOKEN = "5Aep861nwwtoVPEij_zqtjVW0Zq3uKlUCSmgu..M9IGINAjdRK_u13KrIkCEq2FohL5jPybG1zbq6eHNOrbrb_K"
	if inputs["SF_INSTANCE"] == "prod":
		RF_URL = "https://login.salesforce.com/services/oauth2/token"
		SF_URL = "https://wrightsmedia.my.salesforce.com/services/data/"
		RF_KEY = "3MVG9i1HRpGLXp.rDSE.v3G1rnFU5MZ79Fw4x8PNSlHJOxc4O4rTr8kuRlr297VT_nzVuSwKE5EFC1iOUih4i"
		RF_SECRET = "ECE599BE6185D483469DC9143C2E8C05FCE715CCD24FE3AE4021DB7A415754DB"
		RF_TOKEN = "5Aep8612E5JLxJp3ET7HLynuJxh07GDEsxdUIDvzOit9LoccvM60Ym3.lyC8C3qGZdaa4_GropJQRLJ855EL4hr"
	# Get new SalesForce token
	sf_token = get_token(RF_URL,RF_KEY,RF_SECRET,RF_TOKEN)
	
	try:
		# Build query string for Discovery and store the result in _record_
		QUERY = "/query?version=2018-12-03&filter=id%3A%3A" + inputs["article_id"] + "&deduplicate=false&highlight=true&passages=true&passages.count=5&query="
		r = requests.get(inputs["DISC_BASE_URL"] + inputs["COLLECTION_ID"] + QUERY, auth=(inputs["DISC_USER"], inputs["DISC_PASS"]))
		j = r.json()
		#print(j)
		if len(j["results"]) < 1 and "title_id" in inputs and "pub_date" in inputs:
			encoded_string = url_encode(inputs["title_id"])
			print("EXECUTING BACKUP QUERY BY PUB DATE & TITLE:", encoded_string)
			QUERY = '/query?version=2018-12-03&filter=metadata.pub_date::' + str(inputs["pub_date"]) + '%2Cmetadata.title%3A"' + encoded_string + '"&deduplicate=false&highlight=true&passages=true&passages.count=5&query='
			r = requests.get(inputs["DISC_BASE_URL"] + inputs["COLLECTION_ID"] + QUERY, auth=(inputs["DISC_USER"], inputs["DISC_PASS"]))
			j= r.json()
		record = j["results"][0]
	except Exception as err:
		error_message = "DEV ERROR attempting to query Discovery with article id: " + inputs["article_id"]
		print(error_message, err)
		email_error(inputs["email_address"], "", "", "", error_message)
		
		raise
	
	pdf_url = ""
	if(build_pdf(record,inputs["COS_APIKEY"])):
		email_pdf(record,inputs["email_address"])
		pdf_url = salesforce_pdf(sf_token,SF_URL,record)
	#print(record)
	entity_output = ""
	featured_company = "None"
	source = record["metadata"]["feed_name"]
	map_entities = {}
	entities = []
	companies = []
	products = []
	people = []
	product = ""
	title = re.sub(r'[^A-Za-z0-9\s\-\:]',"",record["metadata"]["title"])
	#print("TITLE IS: ", title)
	date = record["metadata"]["pub_date"]
	
	if "entities" in record["enriched_text"] and len(record["enriched_text"]["entities"]) > 0:
		# Go through each entity to pull out Company, Product, and Person entities. Exclude social media companies.
		for entity in record["enriched_text"]["entities"]:
			if (entity["type"] == "Company" or entity["type"] == "Organization")\
					and not (re.search(r'[fF]acebook',entity["text"])) and entity["text"] != "Pinterest"\
					and entity["text"] != "Twitter" and not (re.search(r'\bNast\b', entity["text"]))\
					and not re.search(r'_', entity["text"]) and not (re.search(r'[lL]inked[Ii]n',entity["text"]))\
					and not (re.search(r'[rR]eddit',entity["text"])) and not (re.search(r'[tT]umblr',entity["text"]))\
					and not (re.search(r'[aA]mazon',entity["text"])) and not (re.search(r'[yY]ou[tT]ube',entity["text"]))\
					and not (re.search(r'[Ii]nstagram',entity["text"])) and entity["text"] != record["metadata"]["publisher"]\
					and entity["text"] != record["metadata"]["feed_name"]:
				if entity["text"] in map_entities:
					map_entities[entity["text"]][0] += float(entity["sentiment"]["score"])
					map_entities[entity["text"]][1] += 1
				else:
					map_entities[entity["text"]] = [float(entity["sentiment"]["score"]),1,entity["type"]]
			if entity["type"] == "Product":
				if entity["text"] in map_entities:
					map_entities[entity["text"]][0] += float(entity["sentiment"]["score"])
					map_entities[entity["text"]][1] += 1
				else:
					map_entities[entity["text"]] = [float(entity["sentiment"]["score"]),1,entity["type"]]
			if entity["type"] == "Person":
				if entity["text"] in map_entities:
					map_entities[entity["text"]][0] += float(entity["sentiment"]["score"])
					map_entities[entity["text"]][1] += 1
				else:
					map_entities[entity["text"]] = [float(entity["sentiment"]["score"]),1,entity["type"]]
		
		# Get average scores for each mention of unique entites
		for key in map_entities.keys():
			if map_entities[key][2] == "Company" or map_entities[key][2] == "Organization":
				companies.append((key, map_entities[key][0]/map_entities[key][1]))
			if map_entities[key][2] == "Person":
				people.append((key, map_entities[key][0]/map_entities[key][1]))
			if map_entities[key][2] == "Product":
				products.append((key, map_entities[key][0]/map_entities[key][1]))
			entities.append((key, map_entities[key][0]/map_entities[key][1]))
		
		# Sort entity list by score
		sorted_e = list(reversed(sorted(entities, key=lambda kv: kv[1])))
		
		# Build output string for Entity/Score pairs
		for tup in sorted_e:
			entity_output = entity_output + tup[0] + " : " + str(tup[1]) + "\n"
		
		# Sort companies and products to find the highest score for each type
		if len(companies) > 0:
			sorted_c = list(reversed(sorted(companies, key=lambda kv: kv[1])))
			featured_company = sorted_c[0][0]
		if len(products) > 0:
			sorted_p = list(reversed(sorted(products, key=lambda kv: kv[1])))
			product = sorted_p[0][0]
		else:
			if len(sorted_e) > 0:
				product = sorted_e[0][0]
			else:
				product = ""
			
	#Query Salesforce to find field IDs
	ids = query_salesforce(record["metadata"]["publisher"], record["metadata"]["feed_name"],SF_URL,RF_URL,RF_KEY,RF_SECRET,RF_TOKEN)
	pub_id = ids[0]
	mag_id = ids[1]
	sales_rep = ids[2]
	#print("SALES REP:", sales_rep)
	
	if mag_id == "":
		error_message = "DEV ERROR finding magazine in SalesForce. PUB: " + record["metadata"]["publisher"] + " MAG: " + record["metadata"]["feed_name"]
		print(error_message)
		email_error(inputs["email_address"], title, record["metadata"]["publisher"], record["metadata"]["feed_name"], error_message)
		raise Exception(error_message)
		
	salesforce_ids = {}
	
	if len(companies) < 1:
		companies.append((featured_company, 0.0))
	
	for com in companies:
		# Build SalesForce payload and create lead
		print("CURRENT COMPANY:", com[0])
		data = json.dumps({"Company": com[0],
							"LastName": "RSS Sentiment Analysis",
							"LeadSource": "RSS Project",
							"Rating": record["metadata"]["lead_classifier"] * 100,
							"Description": "Title: " + title +
										"\nSentiment Score: " + str(record["enriched_text"]["sentiment"]["document"]["score"]) +
										"\nClassifier Score: " + str(record["metadata"]["lead_classifier"]) +
										"\nFeatured Product: " + product +
										"\nEntities:\n" + entity_output,
							'Sales_Rep__c': sales_rep,
							'Magazine__c': mag_id,
							'Web_Link__c': record["metadata"]["url"],
							'Magazine_Type__c': "Online",
							'Publisher__c': pub_id,
							'Issue_Date__c': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(record["metadata"]["pub_date"]/1000)),
							'Article_Title__c': title,
							'Featured_Product__c': product,
							'Winning_Company__c': com[0],
							'Company_Short_Name__c': com[0],
							'Published_Rating__c': record["metadata"]["lead_classifier"] * 100,
							'RSS_PDF__c': pdf_url})
		headers = {"Content-Type": "application/json", "Authorization": "Bearer " + sf_token}
		r = requests.post(SF_URL+"v39.0/sobjects/Lead", headers=headers, data=data)
		if r.status_code != 200 and r.status_code != 201:
			error_message = "DEV ERROR during Lead creation in SalesForce"
			print(error_message, r.text)
			email_error(inputs["email_address"], title, record["metadata"]["publisher"], record["metadata"]["feed_name"], error_message)
			raise Exception(error_message)
		else:
			# Gather SalesForce IDs
			j = r.json()
			salesforce_ids[re.sub(r'[ #\.,]',"_",com[0])] = j["id"]

	# Update Discovery with Salesforce Lead IDs and timestamp
	record["metadata"]["salesforce_ids"] = salesforce_ids
	record["metadata"]["salesforce_timestamp"] = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
	UPDATE = "?version=2019-04-30"
	files={"file": record["html"].encode('utf-8'), "metadata": json.dumps(record["metadata"])}
	time_out = 5
	attempts = 1
	while True:
		try:
			r = requests.post(inputs["DISC_BASE_URL"] + inputs["COLLECTION_ID"] + "/documents/" + inputs["article_id"] + UPDATE, auth=(inputs["DISC_USER"], inputs["DISC_PASS"]), files=files)
			r.raise_for_status()
		except Exception as ex:
			if attempts > 1:
				print("DEV LEAD UPDATE TO DISCOVERY FAILED WITH STATUS CODE" + str(r.status_code) + ": " + str(ex))
				print("FULL RESPONSE:",r.text)
				print("METADATA:",record["metadata"])
				raise
			else:
				print("Dev First Try Failure, Retrying in " + str(time_out) + "seconds to upload...")
				time.sleep(time_out)
				time_out = time_out ** 2
				attempts += 1
				continue
		break
	print("DEV LEAD UPDATE DISCOVERY RESULTS",r.text,"METADATA:",record["metadata"])
	return {'message': "Successfully created lead"}

# @DEV: Strips string of chars it can't handle and then encodes given string for safe usage in HTTP URLs
# @PARAM: _to_encode - string to encode
# @RET: Returns URL safe string
def url_encode(_to_encode):
	encoded_string = re.sub(r'[^\w\s\?\#\&\!\"\$\%\(\)\/\:\<\=\>\@\‘\’\-\,\'\\\.\;\—\–]','',_to_encode)
	encoded_string = re.sub(r'\%','%25', encoded_string)
	encoded_string = re.sub(r'\?','%3F', encoded_string)
	encoded_string = re.sub(r'\#','%23', encoded_string)
	encoded_string = re.sub(r'\&','%26', encoded_string)
	encoded_string = re.sub(r'\s','%20', encoded_string)
	encoded_string = re.sub(r'\!','%21', encoded_string)
	encoded_string = re.sub(r'\"','%5C%22', encoded_string)
	encoded_string = re.sub(r'\$','%24', encoded_string)
	encoded_string = re.sub(r'\(','%28', encoded_string)
	encoded_string = re.sub(r'\)','%29', encoded_string)
	encoded_string = re.sub(r'\/','%2F', encoded_string)
	encoded_string = re.sub(r'\:','%3A', encoded_string)
	encoded_string = re.sub(r'\<','%3C', encoded_string)
	encoded_string = re.sub(r'\=','%3D', encoded_string)
	encoded_string = re.sub(r'\>','%3E', encoded_string)
	encoded_string = re.sub(r'\@','%40', encoded_string)
	encoded_string = re.sub(r'\\','%5C', encoded_string)
	encoded_string = re.sub(r'\'','%27', encoded_string)
	encoded_string = re.sub(r'\;','%3B', encoded_string)
	encoded_string = re.sub(r'\—','%E2%80%94', encoded_string)
	encoded_string = re.sub(r'\–','%E2%80%93', encoded_string)
	return encoded_string


# @DEV: Emails information about any errors to a designated address
# @PARAM: _publisher is the string of the publisher
# @PARAM: _magazine is the string of the magazine
# @PARAM: title is the string of the title
# @PARAM addr is the recipient's email address
# @PARAM error_message is a string describing the error encountered
def email_error(addr, title, publisher, magazine, error_message):
	port = 465
	smtp_server = "smtp.gmail.com"
	sender_email = "WM.RSS.mailer@gmail.com"
	receiver_email = addr
	password = "WMmai1B0t!"
	message = """Subject: RSS Feed Lead Error

	An error occurred during lead generation."""
	message = message + "\n\nERROR MESSAGE: " + error_message + "\n\nTITLE: " + title + "\nPUBLISHER: " + publisher + "\nMAGAZINE: " + magazine

	context = ssl.create_default_context()
	with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
		server.login(sender_email, password)
		server.sendmail(sender_email, receiver_email, message)
		
		
# @DEV: Emails Lead pdf to a designated address
# @PARAM: _record is the article data
def email_pdf(record, addr):
	msg = MIMEMultipart()
	msg['From'] = "WM.RSS.mailer@gmail.com"
	msg['To'] = addr
	msg['Date'] = formatdate(localtime=True)
	msg['Subject'] = "New Lead PDF"
	message = """Attached is the Lead for the following Article"""
	message = message + "\n\nTITLE: " + record["metadata"]["title"] + "\nPUBLISHER: " + record["metadata"]["publisher"] + "\nMAGAZINE: " + record["metadata"]["feed_name"]
	msg.attach(MIMEText(message))
	with open(record['id'] + '.pdf', "rb") as f:
		part = MIMEApplication(
			f.read(),
			Name=record['id']+'.pdf'
		)
	part['Content-Disposition'] = 'attachment; filename="%s"' % record['id']+'.pdf'
	msg.attach(part)
	port = 465
	smtp_server = "smtp.gmail.com"
	sender_email = "WM.RSS.mailer@gmail.com"
	receiver_email = addr
	password = "WMmai1B0t!"

	context = ssl.create_default_context()
	with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
		server.login(sender_email, password)
		server.sendmail(sender_email, receiver_email, msg.as_string())

# @DEV: Gets a refreshed access token to SalesForce
# @PARAM _RF_KEY Salesforce Refresh Key
# @PARAM _RF_SECRET Salesforce Secret
# @PARAM _RF_TOKEN Salesforce Refresh Token
# @RET: Returns the refreshed access token
def get_token(RF_URL,RF_KEY,RF_SECRET,RF_TOKEN):
	params = {"grant_type": "refresh_token", "client_id": RF_KEY, "client_secret": RF_SECRET, "refresh_token": RF_TOKEN}
	r = requests.get(RF_URL, params=params)
	return r.json()["access_token"]
	
# @DEV: Queries Salesforce for publisher ID and magazine ID
# @PARAM: _publisher is the string of the publisher
# @PARAM: _magazine is the string of the magazine
# @PARAM: _SF_URL is the Salesforce URL
# @PARAM _RF_KEY Salesforce Refresh Key
# @PARAM _RF_SECRET Salesforce Secret
# @PARAM _RF_TOKEN Salesforce Refresh Token
# @RET: Returns a tuple containing the publisher ID, magazine ID, and sales rep
def query_salesforce(publisher, magazine, SF_URL, RF_URL, RF_KEY, RF_SECRET, RF_TOKEN):
	sf_token = get_token(RF_URL,RF_KEY,RF_SECRET,RF_TOKEN)
	pub_id = ""
	mag_id = ""
	sales_rep = ""
	
	try:
		QUERY = "v20.0/query/?q=SELECT+Account_Id_18__c+from+Account+where+Name+like+'" + re.sub(r'\&','%26',re.sub(r"'", "\\'", publisher)) +"'"
		headers = {"Authorization": "Bearer " + sf_token}
		r = requests.get(SF_URL+QUERY, headers=headers)
		r.raise_for_status()
	except Exception as err:
		print("ERROR QUERYING SF FOR PUB::",err)
	try:
		j = r.json()
	except Exception as err:
		print("ERROR PARSING RAW PUB SF RESPONSE:", r.text)
	try:
		if len(j["records"]) > 0 and len(j["records"]) < 2:
			pub_id = j["records"][0]["Account_Id_18__c"]
	except Exception as err:
		print("Got response but could not find publisher in SalesForce", err)
	
	try:
		QUERY = "v20.0/query/?q=SELECT+Magazine_ID__c+,+ID+,+Sales_Rep__c+from+Magazine__c+where+Name+like+'" + re.sub(r'\&','%26',re.sub(r"'","\\'", magazine)) +"'"
		headers = {"Authorization": "Bearer " + sf_token}
		r = requests.get(SF_URL+QUERY, headers=headers)
		r.raise_for_status()
	except Exception as err:
		print("ERROR QUERYING SF FOR MAG::",err)
	try:
		j = r.json()
	except Exception as err:
		print("RAW MAG QUERY RESPONSE:", r.text)
		print("ERROR:", err)
	try:
		if len(j["records"]) > 0 and len(j["records"]) < 2:
			#print("magazine query output", j["records"][0])
			mag_id = j["records"][0]["Id"]
			sales_rep = j["records"][0]["Sales_Rep__c"]
	except Exception as err:
		print("Got response but could not find magazine in SalesForce", err, "RAW MAG QUERY RESPONSE:", r.text)
	
	return (pub_id, mag_id, sales_rep)
	
	
class PDF(FPDF):

	col = 0
	y0 = 0
	three_col = True
	publisher = ""

	def header(self):
		self.y0 = self.get_y()
		
	def set_col(self, col):
		self.col = col
		x = 10 + col * 65
		self.set_left_margin(x)
		self.set_x(x)
		
	def accept_page_break(self):
		if(not self.three_col):
			return True
		if(self.col < 2):
			self.set_col(self.col + 1)
			self.set_y(self.y0)
			return False
		else:
			self.set_col(0)
			return True
			
	def footer(self):
		self.set_y(-15)
		self.set_font('Helvetica', 'B', 11)
		self.cell(0,10,u'\u00A9'+" "+ str(datetime.now().year)+" "+self.publisher,0,0,'R')
			
def remove_non_ascii(text):
	return ''.join([i if ord(i) < 128 else "?" for i in text])


# @DEV: Builds PDF from article data and writes it to the FS
# @PARAM: record - dictionary of article data
# @PARAM: cos_apikey - Cloud Object Storage apikey
# @RET: Boolean of success or failure of PDF building
def build_pdf(record, cos_apikey):
	article = re.sub(r"no title\s*\n*", "", remove_non_ascii(record['text']))
	if(len(article)<10):
		return False
	wm_logo = "wm-logo"
	mag_logo = re.sub(r'[^\w\.\-]','',record["metadata"]["feed_name"]).lower()
	token = get_cos_token(cos_apikey)
	pdf = PDF()
	pdf.add_font("NotoSans", style="", fname="NotoSans-Regular.ttf", uni=True)
	pdf.add_font("NotoSans", style="B", fname="NotoSans-Bold.ttf", uni=True)
	pdf.add_font("NotoSans", style="I", fname="NotoSans-Italic.ttf", uni=True)
	pdf.add_font("NotoSans", style="BI", fname="NotoSans-BoldItalic.ttf", uni=True)
	pdf.publisher = record['metadata']['publisher']
	pdf.add_page()
	if(get_logo(mag_logo, token)):
		pdf.image(mag_logo+".png",h=15)
	else:
		pdf.set_font('NotoSans', 'B', 20)
		pdf.cell(90,15,record["metadata"]["feed_name"],0,1,'L')
	pdf.set_font('NotoSans', 'B', 18)
	pdf.ln(10)
	pdf.multi_cell(0,10, record["metadata"]["title"], align='C')
	pdf.ln(5)
	pdf.y0 = pdf.get_y()
	pdf.set_font("NotoSans", size=10)
	if(len(article) > 3250):
		pdf.multi_cell(60,5,article)
	else:
		pdf.three_col = False
		pdf.multi_cell(0,5,article)
	pdf.output(record["id"]+'.pdf')
	return True


# @DEV: Gets token for accessing Cloud Object Storage
# @PARAM: cos_apikey - Cloud Object Storage API Key
# @RET: Returns Cloud Object Storage access token
def get_cos_token(cos_apikey):
	headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
	data = {"apikey": cos_apikey, "response_type": "cloud_iam", "grant_type": "urn:ibm:params:oauth:grant-type:apikey"}
	
	r = requests.post("https://iam.cloud.ibm.com/oidc/token", headers=headers, data=data)
	j = r.json()
	return j["access_token"]
	

# @DEV: Downloads Logo PNG from  Cloud Object Storage and writes file to FS
# @PARAM: logo_name - name of logo to download
# @PARAM: token - Cloud Object Storage token
# @RET: Boolean of success or failure of download
def get_logo(logo_name, token):
	service_instance_id = "crn:v1:bluemix:public:cloud-object-storage:global:a/0c8f8500241c4728b578f4a0b6d7f879:b9cd49d0-a8fc-4036-965d-7e5f79cee29b::"

	# request elements
	endpoint = 'https://s3.us-east.cloud-object-storage.appdomain.cloud'
	bucket = 'wm-pdf-logos'
	object_key = logo_name + ".png"
	headers = {"ibm-service-instance-id": service_instance_id, "Authorization": "Bearer " + token}

	standardized_resource = '/' + bucket + '/' + object_key
	request_url = endpoint + standardized_resource
	try:
		r = requests.get(request_url, headers=headers, allow_redirects=True)
		r.raise_for_status()
	except Exception as e:
		print("COULD NOT FIND LOGO WITH LOGO NAME:",logo_name)
		print("ERROR:", str(e))
		return False

	open(object_key, 'wb').write(r.content)
	
	return True


# @DEV: UPloads PDF to Salesforce as Document
# @PARAM: sf_token - token to authenticate with Salesforce
# @PARAM: sf_url - base URL for Salesforce
# @PARAM: record - dictionary of article data
# @RET: String of URL to Salesforce Document
def salesforce_pdf(sf_token,sf_url,record):
	folder_id = "00l0f000002BOduAAG"
	pdf_file = record['id']+'.pdf'
	try:
		QUERY = "v23.0/sobjects/Document/"
		headers = {"Authorization": "Bearer " + sf_token}
		data = {"Description" : "Automatically generated article PDF",
				"Keywords" : "article,lead,pdf",
				"FolderId" : folder_id,
				"Name" : record["id"]+'.pdf',
				"Type" : "pdf"
				}
		files = {"entity_document": (None,json.dumps(data),'application/json'), "Body": (pdf_file, open(pdf_file, 'rb'), 'application/pdf')}
		r = requests.post(sf_url+QUERY, headers=headers, files=files)
		r.raise_for_status()
		j = r.json()
		return re.sub(r'\/services\/data','',sf_url) + j['id']
	except Exception as e:
		print("COULD NOT UPLOAD PDF TO SALESFORCE")
		print("ERROR:", str(e))
		return "" 

def main(dict):
	print("Lead By Article called with parameters:", str(dict))
	return lead_by_article(dict)