import requests
import webbrowser
from requests.auth import HTTPBasicAuth
from slugify import slugify
import os
from datetime import datetime
from datetime import timedelta
import pickle
import local_data


class Auth:
    REDIRECT_URI = local_data.REDIRECT_URI
    CLIENT_ID = local_data.CLIENT_ID
    CLIENT_SECRET = local_data.CLIENT_SECRET

    def __init__(self, scopes):
        self.scopes = scopes
        self.access = None
        self.refresh = None
        self.timeout = None

        self.load()

    def _get_cache_filename(self):
        return ".cache_" + slugify("-".join(self.scopes))

    def load(self):
        filename = self._get_cache_filename()

        if os.path.exists(filename):
            with open(filename, "rb") as file:
                data = pickle.load(file)
                self.scopes = data["scopes"]
                self.access = data["access"]
                self.refresh = data["refresh"]
                self.timeout = data["timeout"]

            self.refresh_if_needed()
        else:
            self.login()

    def save(self):
        filename = self._get_cache_filename()

        data = dict(
            timeout=self.timeout,
            access=self.access,
            refresh=self.refresh,
            scopes=self.scopes,
        )

        with open(filename, "wb") as file:
            pickle.dump(data, file)

    def refresh_if_needed(self):
        if self.timeout > datetime.now():
            return

        api_url = "https://accounts.spotify.com/api/token"

        data = dict(grant_type="refresh_token", refresh_token=self.refresh)

        tokens = requests.post(
            api_url, data=data, auth=HTTPBasicAuth(self.CLIENT_ID, self.CLIENT_SECRET)
        ).json()

        self.access = tokens["access_token"]
        self.refresh = tokens["refresh_token"]
        self.timeout = datetime.now() + timedelta(seconds=(tokens["expires_in"] - 60))

        self.save()

    def get_code(self):
        api_url = "https://accounts.spotify.com/authorize"

        params = dict(
            client_id=self.CLIENT_ID,
            response_type="code",
            redirect_uri=self.REDIRECT_URI,
            scope=" ".join(self.scopes),
            show_dialog=True
        )

        url = requests.Request("GET", api_url, params=params).prepare().url

        webbrowser.open(url)

        code = input("paste code here: ")

        return code

    def get_tokens(self, code):
        api_url = "https://accounts.spotify.com/api/token"

        data = dict(
            code=code, redirect_uri=self.REDIRECT_URI, grant_type="authorization_code"
        )

        tokens = requests.post(
            api_url, data=data, auth=HTTPBasicAuth(self.CLIENT_ID, self.CLIENT_SECRET)
        ).json()

        self.access = tokens["access_token"]
        self.refresh = tokens["refresh_token"]
        self.timeout = datetime.now() + timedelta(seconds=(tokens["expires_in"] - 60))

        self.save()

    def login(self):
        code = self.get_code()
        self.get_tokens(code)

    def get_access_token(self):
        self.refresh_if_needed()
        return self.access

    def _get_auth_header(self):
        self.refresh_if_needed()
        return dict(Authorization="Bearer " + self.access)

    def get_user_id(self):
        url = "https://api.spotify.com/v1/me"

        user_details = requests.get(url, headers=self._get_auth_header()).json()

        return user_details["id"]

    def create_playlist(self, user_id, playlist_name):
        api_url = "https://api.spotify.com/v1/users/{}/playlists".format(user_id)

        data = dict(name=playlist_name, public=False, collaborative=False)

        playlist_details = requests.post(
            api_url, json=data, headers=self._get_auth_header()
        ).json()

        return playlist_details

    def get_playlists(self, user_id):
        api_url = "https://api.spotify.com/v1/users/{}/playlists".format(user_id)

        return requests.get(api_url, headers=self._get_auth_header()).json()

    def get_or_create_playlist(self, user_id, playlist_name):
        playlists = self.get_playlists(user_id)

        for playlist in playlists["items"]:
            print(playlist["name"])
            if playlist["name"] == playlist_name:
                return playlist

        #return self.create_playlist(user_id, playlist_name)


def main():
    auth = Auth(["playlist-modify-private"])
    user_id = auth.get_user_id()
    auth.get_or_create_playlist(user_id, "Essential heavy")


if __name__ == "__main__":
    main()
