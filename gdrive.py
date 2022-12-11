from __future__ import print_function

import os.path
import time

from pychatgpt import Chat, Options

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/documents.readonly',
          'https://www.googleapis.com/auth/drive.readonly']

# The ID of a sample document.
DOCUMENT_ID = '1qPJ_sb9W0VhdpsFXhOQP9BFbLVK4dIpvr8alG_mHblU' # my single transcript

credential_json = 'app_credential.json'


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
        <very short summary of most recent point made>

        Transcript:

        """

    creds = get_credentials(force=False)
    chat = get_gpt_chat()

    try:
        ## This part is an experiement to read files to try and find the transcript
        # good for file selection in js https://developers.google.com/drive/picker/guides/overview
        # for now, hardcoded as DOCUMENT_ID

        # drive_service = build('drive', 'v3', credentials=creds)
        # files = []
        # page_token = None
        # while True:
        #     response = drive_service.files().list(
        #         q="mimeType='image/jpeg'",
        #         spaces='drive',
        #         fields='nextPageToken, files(id, name)',
        #         pageToken=page_token).execute()
        #     for file in response.get('files', []):
        #         # Process change
        #         print(F'Found file: {file.get("name")}, {file.get("id")}')
        #     files.extend(response.get('files', []))
        #     page_token = response.get('nextPageToken', None)
        #     if page_token is None:
        #         break
        
    

        ## This part reads DOCUMENT_ID and prints everything
        doc_service = build('docs', 'v1', credentials=creds)


    except HttpError as err:
        print(err)


    action_items = []
    main_points = []

    i = 0
    while True:
        i += 1
        # Retrieve the documents contents from the Docs service.
        document = doc_service.documents().get(documentId=DOCUMENT_ID).execute()

        doc_content = document.get('body').get('content')
        transcript = read_structural_elements(doc_content)

        # TODO: check to see if there's new information in the transcript before sending to chat gpt
        prompt = prompt_header + transcript
        answer = chat.ask(prompt)

        # Things to track and maintain:
        # Recent transcript: Last few words
        # Recent summary: Summary of most recent thing said
        # Action items: This should be a list that just keep appending on new action items when chat runs
        # Main points: Operates the same way as action items
        resp_groups = split(answer[0], ['Main Points:', 'Action Items:', 'Recent Summary:'])
        
        # ensure no duplicates, this way isn't as pretty, but it maintains order
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