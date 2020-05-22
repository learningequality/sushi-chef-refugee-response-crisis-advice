#!/usr/bin/env python
import os
import sys
import logging
import youtube_dl
import argparse

from ricecooker.chefs import SushiChef
from ricecooker.classes import nodes, files, questions, licenses
from ricecooker.classes.files import YouTubeVideoFile
from ricecooker.classes.nodes import VideoNode, TopicNode
from ricecooker.classes.licenses import get_license
from ricecooker.exceptions import raise_for_invalid_channel
from le_utils.constants import exercises, content_kinds, file_formats, format_presets, languages
from pressurecooker.youtube import YouTubeResource

from utils import *
from google_sheet_utils import *

LOGGER = logging.getLogger("RefugeeResponseSushiChef")
LOGGER.setLevel(logging.DEBUG)

# Run constants
################################################################################
CHANNEL_NAME = "Crisis Advice from the Refugee Response"
CHANNEL_DOMAIN = "refugeeresponse.org"
CHANNEL_LANGUAGE = "mul"                                     # Default language of the channel
CHANNEL_SOURCE_ID = "refugee-response"                              # Channel's unique id
CHANNEL_DESCRIPTION = "Short video lessons on managing education, mental health, public health, COVID-19 questions, and more topics for building general knowledge and succeeding in a new environment."
CHANNEL_THUMBNAIL = None                                    # Local path or url to image file (optional)

# Additional constants
################################################################################
LANGUAGE_KEYNAME = "--lang"
NO_CACHE_KEYNAME = "--nocache"
DOWNLOAD_TO_GOOGLE_SHEET_KEYNAME = "--tosheet"
REFUGEE_RESPONSE = "Refugee Response"
YOUTUBE_VIDEO_URL_FORMAT = "https://www.youtube.com/watch?v={0}"
TOPIC_NAME_FORMAT = "Crisis Advice from the Refugee Response ({0})"

# The chef subclass
################################################################################
class RefugeeResponseSushiChef(SushiChef):
    """
    This class uploads the {{ cookiecutter.channel_name }} channel to Kolibri Studio.
    Your command line script should call the `main` method as the entry point,
    which performs the following steps:
      - Parse command line arguments and options (run `./sushichef.py -h` for details)
      - Call the `SushiChef.run` method which in turn calls `pre_run` (optional)
        and then the ricecooker function `uploadchannel` which in turn calls this
        class' `get_channel` method to get channel info, then `construct_channel`
        to build the contentnode tree.
    For more info, see https://github.com/learningequality/ricecooker/tree/master/docs
    """
    channel_info = {                                   # Channel Metadata
        'CHANNEL_SOURCE_DOMAIN': CHANNEL_DOMAIN,       # Who is providing the content
        'CHANNEL_SOURCE_ID': CHANNEL_SOURCE_ID,        # Channel's unique id
        'CHANNEL_TITLE': CHANNEL_NAME,                           # Name of channel
        'CHANNEL_LANGUAGE': CHANNEL_LANGUAGE,          # Language of channel
        'CHANNEL_THUMBNAIL': CHANNEL_THUMBNAIL,        # Local path or url to image file (optional)
        'CHANNEL_DESCRIPTION': CHANNEL_DESCRIPTION,    # Description of the channel (optional)
    }
    use_cache = True   # field to indicate whether use cached json data
    to_sheet = False

    def construct_channel(self, *args, **kwargs):
        """
        Creates ChannelNode and build topic tree
        Args:
          - args: arguments passed in on the command line
          - kwargs: extra options passed in as key="value" pairs on the command line
            For example, add the command line option   lang="fr"  and the value
            "fr" will be passed along to `construct_channel` as kwargs['lang'].
        Returns: ChannelNode
        """
        # Update language info from option input
        global CHANNEL_NAME, CHANNEL_LANGUAGE
        for key, value in kwargs.items():
          # if key == LANGUAGE_KEYNAME:
          #   CHANNEL_LANGUAGE = value
          #   LOGGER.info("Input language: '%s'", CHANNEL_LANGUAGE)
          if key == NO_CACHE_KEYNAME:
            self.use_cache = False
            LOGGER.info("use_cache = '%d'", self.use_cache)
          if key == DOWNLOAD_TO_GOOGLE_SHEET_KEYNAME:
            self.to_sheet = True
            LOGGER.info("to_sheet = '%d'", self.to_sheet)
        
        if self.to_sheet:
          upload_description_to_google_sheet(self.use_cache)
          exit(0)

        channel = self.get_channel(*args, **kwargs)  # Create ChannelNode from data in self.channel_info

        # Get YouTube playlist URL by language
        for lang, id_list in PLAYLIST_MAP.items():
          rr_lang_obj = RefugeeResponseLanguage(name=lang, code=lang)
          if not rr_lang_obj.get_lang_obj():
            raise RefugeeResponseLangInputError("Invalid Language: " + lang)

          if id_list is not None and len(id_list) > 0:
            playlist_id = id_list[0]
            topic_node = TopicNode(
              title=TOPIC_NAME_FORMAT.format(rr_lang_obj.name),
              source_id='refugeeresponse-child-topic-{0}'.format(rr_lang_obj.code),
              language=rr_lang_obj.code
            )
            download_video_topics(topic_node, playlist_id, rr_lang_obj, self.use_cache)
            channel.add_child(topic_node)
          else:
            raise RefugeeResponseConfigError("Empty playlist info for language: " + lang)
          
          raise_for_invalid_channel(channel)  # Check for errors in channel construction
          return channel    
        
def download_video_topics(topic_node, playlist_id, lang_obj, use_cache = True, to_sheet = False):
  """
  Scrape, collect, and download the videos from playlist.
  """
  playlist_info = get_playlist_info(playlist_id, use_cache)
  videos = [entry['id'] for entry in playlist_info.get('children')]
  for video in videos:
    try:
      video_url = YOUTUBE_VIDEO_URL_FORMAT.format(video)
      rr_video_obj = RefugeeResponseVideo(
                      url=video_url,
                      language=lang_obj.code
                    )
      if rr_video_obj.download_info(use_cache):
        LOGGER.info("Success download video with title: %s", rr_video_obj.title)
        video_source_id = 'refugee-response-{0}'.format(video)
        video_node = VideoNode(
          source_id=video_source_id, 
          title=rr_video_obj.title,
          description=rr_video_obj.description,
          author=REFUGEE_RESPONSE,
          thumbnail=rr_video_obj.thumbnail,
          license=get_license("CC BY-NC-ND", copyright_holder=REFUGEE_RESPONSE),
          files=[
            YouTubeVideoFile(
              youtube_id=video,
              language=rr_video_obj.language
            )
          ])
        topic_node.add_child(video_node)
      else:
        LOGGER.error("Failed to download video")
    except Exception as e:
      print('Error downloading this video:', e)

def upload_description_to_google_sheet(use_cache = True):
  """
  Fetch and update video description to Google spreadsheet
  """
  google_sheet_obj = RefugeeResponseSheetWriter(SPREADSHEET_ID)
  for lang, id_list in PLAYLIST_MAP.items():
    rr_lang_obj = RefugeeResponseLanguage(name=lang, code=lang)
    if not rr_lang_obj.get_lang_obj():
      raise RefugeeResponseLangInputError("Invalid Language: " + lang)

    if id_list is not None and len(id_list) > 0:
      playlist_id = id_list[0]
      playlist_info = get_playlist_info(playlist_id, use_cache)
      if playlist_info is None:
        LOGGER.error("Invalid video playlist: %s", playlist_id)
        raise RefugeeResponseConfigError("Invalid playlist: " + playlist_id)

      videos = playlist_info.get('children')
      if videos is None:
        LOGGER.error("Invalid video playlist: %s", playlist_id)
        raise RefugeeResponseConfigError("Invalid playlist: " + playlist_id)
      
      for video_info in playlist_info.get('children'):
        record = RefugeeResponseDescriptionRecord(video_info['id'],
                                                  video_info['source_url'],
                                                  video_info['description'],
                                                  rr_lang_obj.name,
                                                  video_info['title'])
        google_sheet_obj.write_description_record(record)
    else:
      raise RefugeeResponseConfigError("Empty playlist info for language: " + lang)
  
  # After done with adding records, clear records from previous writing
  #  google_sheet_obj.clear_old_records()

# CLI
#################################################################################
if __name__ == '__main__':
  chef = RefugeeResponseSushiChef()
  chef.main()
