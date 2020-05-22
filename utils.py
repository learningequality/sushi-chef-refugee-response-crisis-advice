import json
import os
import re
import logging
import youtube_dl

from pressurecooker.youtube import YouTubeResource
from le_utils.constants.languages import getlang_by_name, getlang

LOGGER = logging.getLogger("RefugeeResponseUtils")
LOGGER.setLevel(logging.DEBUG)

YOUTUBE_CACHE_DIR = os.path.join('chefdata', 'youtubecache')
YOUTUBE_ID_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?(?P<youtube_id>[A-Za-z0-9\-=_]{11})'
)
YOUTUBE_PLAYLIST_URL_FORMAT = "https://www.youtube.com/playlist?list={0}"

PLAYLIST_MAP = {
  # "en": [
  #   "PLOZioxrIwCv0zNRqCsTN979Ez3jBRQiNN"
  # ],
  # "ru": [
  #   "PLOZioxrIwCv3SW4keysO7tO2bMnHlkE8h"
  # ],
  # "ar": [
  #   "PLOZioxrIwCv3WqpQzBrn2_qHhyVsWjErq"
  # ],
  # "es": [
  #   "PLOZioxrIwCv07eahemHM6wGvCePv6B6X8"
  # ],
  "som": [
    "PLOZioxrIwCv2lOyXZPuW213wF1nXQmKUM"
  ],
  # "ne": [
  #   "PLOZioxrIwCv0q8q6KQBlX0hBIl1ZfE268"
  # ],
  # "rw": [
  #   "PLOZioxrIwCv329B1jr2GG7CPhpMTSYVQG"
  # ],
  # "my": [
  #   "PLOZioxrIwCv3a7_cWltapDop8tm2_eyXa"
  # ],
  # "ps": [
  #   "PLOZioxrIwCv2ZJQvlXLg-uMPTQpvx5kDE"
  # ],
  # "sw": [
  #   "PLOZioxrIwCv10xetpSpX296rsIEs2mb67"
  # ],
  # "uk": [
  #   "PLOZioxrIwCv3XpPncjdUrwuoB2jlgZ2no"
  # ],
  # "Kachin": [
  #   "PLOZioxrIwCv2qOS16EQeuy8vcp7ri5p07"
  # ],
  # "Rohingya": [
  #   "PLOZioxrIwCv33zt5aFFjWqDoEMm55MVA9"
  # ],
  # "Karenni": [
  #   "PLOZioxrIwCv03K3kD4hP8ltoX3QOsFLNP"
  # ],
  # "Karen": [
  #   "PLOZioxrIwCv3-N46sJG8QZnHT4G4s4KDk"
  # ]
}

# List of languages not avialble at the le_utils
UND_LANG = {
    "kachin": {
        "name": "Kachin",
        "native_name": "ကချင်ဘာသာ, kachin, jingpho",
        "code": "und"
    },
    "rohingya": {
        "name": "Rohingya",
        "native_name": "Ruáingga",
        "code": "und",
    },
    "karenni": {
        "name": "Karenni",
        "native_name": "Red Karen, Karenni, Kayah",
        "code": "und",
    },
    "karen": {
      "name": "Karen",
      "native_name": "karen",
      "code": "und",
    }
}

class RefugeeResponseError(Exception):
  pass

class RefugeeResponseLangInputError(RefugeeResponseError):
    def __init__(self, message):
        self.message = message

class RefugeeResponseConfigError(RefugeeResponseError):
    def __init__(self, message):
        self.message = message


class RefugeeResponseLanguage():
  name = ''
  code = ''
  native_name = ''

  def __init__(self, name='', code='', native_name=''):
    self.name = name.lower()
    self.code = code
    self.native_name = native_name

  def set_value(self, name, code, native_name):
    self.name = name
    self.code = code
    self.native_name = native_name

  def get_lang_obj(self):
    if self.name != "":
      lang_code = self.code
      lang_name = self.name
      language_obj = getlang_by_name(lang_name) if not getlang(lang_name) else getlang(lang_name)

      if not language_obj:
        if UND_LANG[self.name]:
          self.set_value(UND_LANG[self.name]["name"],
                         UND_LANG[self.name]["code"],
                         UND_LANG[self.name]["native_name"])
          return True
      else:
        self.set_value(language_obj.name, language_obj.code,
                       language_obj.native_name)
        return True
    else:
      return False


class RefugeeResponseVideo():

  uid = 0  # value from `id` after `youtube_dl.extract_info()`
  title = ''
  description = ''
  url = ''
  language = ''
  thumbnail = ''  # local path to thumbnail image
  license = ''
  license_common = False

  def __init__(
      self,
      uid=0,
      url='',
      title='',
      description='',
      language='',
  ):
    self.uid = str(uid)
    self.url = url
    self.title = title
    self.description = description
    self.thumbnail = None
    self.language = language
    self.license_common = False

  def __str__(self):
    return 'RefugeeResponseVideo (%s - %s - %s)' % (self.uid, self.url,
                                                    self.title)

  def download_info(self, use_cache=True):

    match = YOUTUBE_ID_REGEX.match(self.url)
    if not match:
      LOGGER.error('==> URL ' + self.url + ' does not match YOUTUBE_ID_REGEX')
      return False
    youtube_id = match.group('youtube_id')
    if not os.path.isdir(YOUTUBE_CACHE_DIR):
      os.mkdir(YOUTUBE_CACHE_DIR)
    vinfo_json_path = os.path.join(YOUTUBE_CACHE_DIR, youtube_id + '.json')
    # First try to get from cache:
    vinfo = None
    if os.path.exists(vinfo_json_path) and use_cache:
      vinfo = json.load(open(vinfo_json_path))
      LOGGER.info("Retrieving cached video information...")
    # else get using youtube_dl:
    if not vinfo:
      LOGGER.info("Downloading %s from youtube...", self.url)
      try:
        video = YouTubeResource(self.url)
      except youtube_dl.utils.ExtractorError as e:
        if "unavailable" in str(e):
          LOGGER.error("Video not found at URL: %s", self.url)
          return False

      if video:
        try:
          vinfo = video.get_resource_info( dict(no_playlist=True, ignore_errors=True) )
          # Save the remaining "temporary scraped values" of attributes with actual values
          # from the video metadata.
          json.dump(vinfo,
                    open(vinfo_json_path, 'w'),
                    indent=4,
                    ensure_ascii=False,
                    sort_keys=True)
        except Exception as e:
          LOGGER.error("Failed to get video info: %s", e)
          return False

      else:
        return False

    self.uid = vinfo[
        'id']  # video must have id because required to set youtube_id later
    self.title = vinfo.get('title', '')
    self.description = vinfo.get('description', '')
    if not vinfo['license']:
      self.license = "Licensed not available"
    elif "Creative Commons" in vinfo['license']:
      self.license_common = True
    else:
      self.license = vinfo['license']

    return True

def get_playlist_info(playlist_id, use_cache=True):
  """
  Get playlist info from either local json cache or URL
  """
  if not os.path.isdir(YOUTUBE_CACHE_DIR):
    os.mkdir(YOUTUBE_CACHE_DIR)
  playlist_info_json_path = os.path.join(YOUTUBE_CACHE_DIR, playlist_id + '.json')

  playlist_info = None
  if os.path.exists(playlist_info_json_path) and use_cache:
    playlist_info = json.load(open(playlist_info_json_path))
    LOGGER.info("Retrieving cached playlist information...")

  if not playlist_info:
    playlist_url = YOUTUBE_PLAYLIST_URL_FORMAT.format(playlist_id)
    playlist_resource = YouTubeResource(playlist_url)

    if playlist_resource:
      try:
        playlist_info = playlist_resource.get_resource_info( dict(no_playlist=True, ignore_errors=True, skip_download=True) )
        # Save the remaining "temporary scraped values" of attributes with actual values
        # from the video metadata.
        json.dump(playlist_info,
                  open(playlist_info_json_path, 'w'),
                  indent=4,
                  ensure_ascii=False,
                  sort_keys=False)
        return playlist_info
      except Exception as e:
        LOGGER.error("Failed to get playlist info: %s", e)
        return None

  return playlist_info