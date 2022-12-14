from __future__ import print_function

import os.path
import datetime

from pychatgpt import Chat, Options

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/documents.readonly',
          'https://www.googleapis.com/auth/drive.readonly']


credential_json = 'app_credential.json'

def parsetime(isotimestring):
    isotimestring = isotimestring.split("T")[1]
    time_string = ":".join(isotimestring.split(":")[:-1])
    # print("#################")
    print(time_string)
    # print("#################")
    return datetime.datetime.strptime(time_string, "%H:%M")

def filter_file(files, isotime):
    sorted(files, key=lambda x: parsetime(x["createdTime"]), reverse=True)
    for f in files:
        # 'createdTime': '2022-12-10T20:28:28.214Z'
        file_date = f["name"].split("-")[0].split(" ")[0]
        file_time = f["name"].split("-")[0].split(" ")[1]
        user_date = isotime.split(" ")[0]
        user_time = isotime.split(" ")[1]
        if file_date == user_date:
            print("$$$$$$$$$$$$$$$$$$$$$")
            d1=datetime.datetime.strptime(user_time,'%H:%M')
            d2=datetime.datetime.strptime(file_time,'%H:%M')
            delta = d1 - d2
            if delta.seconds < 300:
                print("########## Success ############")
                return f
        
def get_folder(creds):
    drive_service = build('drive', 'v3', credentials=creds)

    # first find the transcript folder
    results = drive_service.files().list(
        q="mimeType = 'application/vnd.google-apps.folder' and fullText contains 'Meet Transcript'",
        spaces='drive',
        pageSize=100,
        fields="nextPageToken,files(id,name, createdTime, modifiedTime)").execute()
    folders = results.get('files', [])

    if folders is None:
        raise Exception("Meet Transcript folder not found within google drive! You need to start a Google Meet and a transcript!\nDownload transcript generation app here: https://chrome.google.com/webstore/detail/meet-transcript/jkdogkallbmmdhpdjdpmoejkehfeefnb?hl=en")

    assert len(folders) == 1
    return folders[0]['id']

def get_most_recent_transcript_id(creds, folder_id, datetime):
    drive_service = build('drive', 'v3', credentials=creds)

    # Use the transcript folder to query for the most recent document
    query = "mimeType='application/vnd.google-apps.document' and '" + folder_id + "' in parents"
    results = drive_service.files().list(
        q=query,
        spaces='drive',
        pageSize=5,
        fields="nextPageToken, files(id,name, createdTime, modifiedTime)").execute()
    files = results.get('files', [])

    # NOTE: results are sorted by recent first.
    if len(files) > 0:
        id = filter_file(files, isotime=datetime)
        return id

    return None

def read_paragraph_element(element):
    """Returns the text in the given ParagraphElement.

        Args:
            element: a ParagraphElement from a Google Doc.
    """
    text_run = element.get('textRun')
    if not text_run:
        return ''
    return text_run.get('content')


def read_structural_elements(elements):
    """Recurses through a list of Structural Elements to read a document's text where text may be
        in nested elements.

        Args:
            elements: a list of Structural Elements.
    """
    text = ''
    for value in elements:
        if 'paragraph' in value:
            elements = value.get('paragraph').get('elements')
            for elem in elements:
                text += read_paragraph_element(elem)
        elif 'table' in value:
            # The text in table cells are in nested Structural Elements and tables may be
            # nested.
            table = value.get('table')
            for row in table.get('tableRows'):
                cells = row.get('tableCells')
                for cell in cells:
                    text += read_structural_elements(cell.get('content'))
        elif 'tableOfContents' in value:
            # The text in the TOC is also in a Structural Element.
            toc = value.get('tableOfContents')
            text += read_structural_elements(toc.get('content'))
    return text

def get_credentials(force=False):
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth 2.0 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if not force and os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credential_json, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds

def get_gpt_chat(email=None, password=None):
    """
    Don't forget to install gpt chat!
    $ pip install chatgptpy --upgrade
    """
    options = Options()
    options.log = True
    options.track = True
    if email is None or password is None:
        raise Exception('Please enter your OpenAI Credentials')

    # Create a Chat object
    return Chat(email=email, password=password, options=options)

def split(txt, seps):
    """
    Splits a string with multiple delimiters
    """
    default_sep = seps[0]

    # we skip seps[0] because that's the default separator
    for sep in seps[1:]:
        txt = txt.replace(sep, default_sep)
    return [i.strip() for i in txt.split(default_sep)]

def main():
    """Shows basic usage of the Docs API.
    Prints the title of a sample document.
    """

    prompt_header = f""" 
        Summarize the following transcript. Write using the following format. Replace everything in <> brackets.

        Main Points:
        - <main point 1>
        - <main point 2>
        - <and so on>

        Action Items:
        - <action 1>
        - <action 2>
        - <and so on>

        Recent Summary: 
        <very short summary of the transcript>

        Transcript:

        """

    creds = get_credentials(force=False)
    chat = get_gpt_chat(email="mail@mail.com", password="password")

    try:
        # TODO option that allows user to select the document
        transcript_id = get_most_recent_transcript_id(creds)

        ## This part reads DOCUMENT_ID and prints everything
        doc_service = build('docs', 'v1', credentials=creds)


    except HttpError as err:
        print(err)


    action_items = []
    main_points = []

    while True:
        # Retrieve the documents contents from the Docs service.
        document = doc_service.documents().get(documentId=transcript_id).execute()
        
        doc_content = document.get('body').get('content')
        transcript = read_structural_elements(doc_content)

        # TODO: check to see if there's new information in the transcript before sending to chat gpt
        prompt = prompt_header + transcript
        # print(prompt)
        answer = chat.ask(prompt)

        ## Things to track and maintain while running:
        # Action items:       A list that keep appending new action items
        # Main points:        Operates the same as action items
        # Recent summary:     Summary of most recent thing said
        # Recent transcript:  Last few words
        resp_groups = split(answer[0], ['Main Points:', 'Action Items:', 'Recent Summary:'])
        
        # TODO don't append if main points or actions == none
        #      `- None mentioned`, `- None specified.`, `- No action items were discussed.`
        #      `- No main points were discussed.`
        # TODO check if len(main_points) == 0 and write a default response

        # Ensure no duplicates. this way isn't pretty, but it maintains order
        for point in resp_groups[1].split('\n'):
            # TODO: better comparison
            if point not in main_points:
                main_points.append(point)
        
        for action in resp_groups[2].split('\n'):
            if action not in action_items:
                action_items.append(action)

        summary = resp_groups[3]

        print('\n\n\n\n')
        print("\nAction Items")
        print("\n".join(action_items))
        print("\nMain Points")
        print("\n".join(main_points))
        print("\nRecent Summary")
        print(summary)
        print("\nRecent Transcript:")
        print(" ".join(transcript.split(' ')[-20:]))

        # don't overload chat gpt?
        time.sleep(10)


if __name__ == '__main__':
    main()