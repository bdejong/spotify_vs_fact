import requests
import webbrowser
from requests.auth import HTTPBasicAuth
from slugify import slugify
import os
from datetime import datetime
from datetime import timedelta
import pickle
import local_data
import urllib
import json
import lxml.html
from cssselect import GenericTranslator, SelectorError

def print_structure(data):
    print(json.dumps(data, indent=4))

def chunks(items, chunk_size):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]

def get_ambient():
    expression = GenericTranslator().css_to_xpath('div.entry-content > hr + p + p strong')
    expression2 = GenericTranslator().css_to_xpath('strong a')
    content = requests.get("https://www.factmag.com/2018/12/16/best-ambient-2018/").text
    xml_tree = lxml.html.fromstring(content)
    albums = []
    
    for element in xml_tree.xpath(expression):
        if element.xpath(expression2):
            text_content = element.text_content()
            if text_content.startswith("Read next"):
                continue
            artist = text_content.split("\n")[0]
            album = element.xpath(expression2)[0].text_content()
            albums.append((artist, album))
    
    return albums
    
def get_best_albums():
    expression1 = GenericTranslator().css_to_xpath(".fr_list_heading.fr-text p")
    expression2 = GenericTranslator().css_to_xpath(".fr_list_sub_heading.fr-text p")
    content = requests.get("https://www.factmag.com/2018/12/13/the-50-best-albums-of-2018/").text
    xml_tree = lxml.html.fromstring(content)
    artists = [element.text_content() for element in xml_tree.xpath(expression1)]
    albums = [element.text_content() for element in xml_tree.xpath(expression2)]
    return zip(artists, albums)

class SpotifyException(Exception):
    pass

class Spotify:
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

    def _raise_if_error(self, data, message="Spotify excepton"):
        if "error" in data:
            raise SpotifyException(message + ": " + data["error"]["message"])

    def refresh_if_needed(self):
        if self.timeout > datetime.now():
            return

        api_url = "https://accounts.spotify.com/api/token"

        data = dict(grant_type="refresh_token", refresh_token=self.refresh)

        tokens = requests.post(
            api_url, data=data, auth=HTTPBasicAuth(self.CLIENT_ID, self.CLIENT_SECRET)
        ).json()

        self._raise_if_error(tokens)

        self.access = tokens["access_token"]
        self.timeout = datetime.now() + timedelta(seconds=(tokens["expires_in"] - 60))

        self.save()

    def get_code(self):
        api_url = "https://accounts.spotify.com/authorize"

        params = dict(
            client_id=self.CLIENT_ID,
            response_type="code",
            redirect_uri=self.REDIRECT_URI,
            scope=" ".join(self.scopes),
            show_dialog=True,
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

        self._raise_if_error(tokens)

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

        self._raise_if_error(user_details)

        return user_details["id"]

    def create_playlist(self, user_id, playlist_name):
        api_url = "https://api.spotify.com/v1/users/{}/playlists".format(user_id)

        data = dict(name=playlist_name, public=False, collaborative=False)

        playlist_details = requests.post(
            api_url, json=data, headers=self._get_auth_header()
        ).json()

        self._raise_if_error(playlist_details)

        return playlist_details

    def get_playlists(self, user_id):
        api_url = "https://api.spotify.com/v1/users/{}/playlists".format(user_id)

        playlists = requests.get(
            api_url, params=dict(limit=50), headers=self._get_auth_header()
        ).json()

        self._raise_if_error(playlists)

        return playlists

    def get_or_create_playlist(self, user_id, playlist_name):
        playlists = self.get_playlists(user_id)

        for playlist in playlists["items"]:
            if playlist["name"] == playlist_name:
                return playlist

        return self.create_playlist(user_id, playlist_name)

    def insert_track(self, playlist_id, track_ids):
        api_url = "https://api.spotify.com/v1/playlists/{}/tracks".format(playlist_id)

        data = dict(uris=track_ids)

        playlist_details = requests.post(
            api_url, json=data, headers=self._get_auth_header()
        ).json()

        self._raise_if_error(playlist_details)

        return playlist_details

    def search_album(self, artist, album):
        api_url = "https://api.spotify.com/v1/search"

        query = "album:{} artist:{}".format(album, artist)
        params = dict(q=query, type="album")

        results = requests.get(
            api_url, params=params, headers=self._get_auth_header()
        ).json()

        self._raise_if_error(results)

        return results

    def get_album_details(self, album_id):
        api_url = "https://api.spotify.com/v1/albums/{}".format(album_id)

        album_details = requests.get(api_url, headers=self._get_auth_header()).json()

        self._raise_if_error(album_details)

        return album_details
    
    def add_albums_to_playlist(self, album_ids, playlist_id):
        tracks = []
        
        for album_id in album_ids:
            album = self.get_album_details(album_id)
            
            for track in album["tracks"]["items"]:
                tracks.append(track["uri"])

        for chunked_tracks in chunks(tracks, 100): # spotify accepts 100 tracks max
            self.insert_track(playlist_id, chunked_tracks)


def main():
    scopes = [
        "user-read-private",
        "playlist-read-private",
        "playlist-modify-public",
        "playlist-modify-private",
    ]
    spotify = Spotify(scopes)

    user_id = spotify.get_user_id()

    if False:
        playlist = spotify.get_or_create_playlist(user_id, "FactMag Ambient")
        playlist_id = playlist["id"]

        album_ids = []
        for (artist, album) in get_ambient():
            albums = spotify.search_album(artist, album)

            if albums["albums"]["items"]:
                album_ids.append(albums["albums"]["items"][0]["id"])
            else:
                print("Did not find", artist, album)
        
        spotify.add_albums_to_playlist(album_ids, playlist_id)
    
    if True:
        playlist = spotify.get_or_create_playlist(user_id, "FactMag Best Albums")
        playlist_id = playlist["id"]

        album_ids = []
        for (artist, album) in get_best_albums():
            albums = spotify.search_album(artist, album)

            if albums["albums"]["items"]:
                album_ids.append(albums["albums"]["items"][0]["id"])
            else:
                print("Did not find", artist, album)
        
        spotify.add_albums_to_playlist(album_ids, playlist_id)



if __name__ == "__main__":
    main()
