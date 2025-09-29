from django.shortcuts import render
import json
import time
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Create your views here.


def index(request):

    context = {}
    return render(request, 'index.html',context)





class HeyGenAPIClient:
    """
    HeyGen API client for text-to-video generation with AI avatars
    """
    def __init__(self, api_key: str):
        self.api_key = os.getenv("HYGEN_API_KEY")
        self.base_url = "https://api.heygen.com"
        self.headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def list_avatars(self):
        """Get list of available avatars"""
        endpoint = f"{self.base_url}/v2/avatars"
        
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error listing avatars: {e}")
            return None
    
    def list_voices(self):
        """Get list of available voices"""
        endpoint = f"{self.base_url}/v2/voices"
        
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error listing voices: {e}")
            return None
    
    def generate_video(self, text: str, avatar_id: str = None, 
                      voice_id: str = None, width: int = 1280, 
                      height: int = 720) -> dict:
        """
        Generate video with HeyGen API
        """
        endpoint = f"{self.base_url}/v2/video/generate"
        
        # Default avatar and voice if not provided
        if not avatar_id:
            avatar_id = "Lina_Dress_Sitting_Side_public"  # Default avatar
        if not voice_id:
            voice_id = "119caed25533477ba63822d5d1552d25"  # Default English voice
        
        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal"
                    },
                    "voice": {
                        "type": "text",
                        "input_text": text[:1500],  # Max 1500 characters
                        "voice_id": voice_id,
                        "speed": 1.0
                    }
                }
            ],
            "dimension": {
                "width": width,
                "height": height
            }
        }
        
        try:
            logger.info(f"Sending request to: {endpoint}")
            logger.info(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(
                endpoint, 
                json=payload, 
                headers=self.headers,
                timeout=30
            )
            
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response: {response.text}")
            
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('error'):
                raise Exception(f"API Error: {result['error']}")
            
            return result
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            raise Exception(f"Failed to connect to API: {str(e)}")
    
    def check_status(self, video_id: str) -> dict:
        """
        Check video generation status
        """
        endpoint = f"{self.base_url}/v1/video_status.get"
        params = {"video_id": video_id}
        
        try:
            response = requests.get(
                endpoint, 
                params=params,
                headers=self.headers,
                timeout=30
            )
            
            logger.info(f"Status check response: {response.status_code}")
            logger.info(f"Status: {response.text}")
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Status check error: {e}")
            raise Exception(f"Failed to check status: {str(e)}")
    
    def wait_for_completion(self, video_id: str, max_wait: int = 300, 
                          poll_interval: int = 5) -> dict:
        """
        Wait for video generation to complete
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                result = self.check_status(video_id)
                
                if result.get('code') != 100:
                    logger.error(f"API returned error code: {result}")
                    return {
                        'success': False,
                        'error': result.get('message', 'Unknown error'),
                        'status': 'failed'
                    }
                
                data = result.get('data', {})
                status = data.get('status')
                
                logger.info(f"Current status: {status}")
                
                if status == 'completed':
                    return {
                        'success': True,
                        'video_url': data.get('video_url'),
                        'thumbnail_url': data.get('thumbnail_url'),
                        'duration': data.get('duration'),
                        'status': status
                    }
                elif status == 'failed':
                    error_info = data.get('error', {})
                    return {
                        'success': False,
                        'error': error_info.get('message', 'Video generation failed'),
                        'status': status
                    }
                
                # Still processing (waiting, pending, processing)
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error during status check: {str(e)}")
                time.sleep(poll_interval)
        
        # Timeout
        return {
            'success': False,
            'error': 'Video generation timed out',
            'status': 'timeout'
        }


@require_http_methods(["POST"])
@csrf_exempt
def generate_video(request):
    """
    Django view to handle HeyGen video generation requests
    
    Expected JSON payload:
    {
        "prompt": "Text for the avatar to speak",
        "avatar_id": "optional_avatar_id",
        "voice_id": "optional_voice_id"
    }
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        logger.info(f"Received request: {data}")
        
        # Get text prompt
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({
                'success': False,
                'error': 'Prompt is required'
            }, status=400)
        
        # Validate text length
        if len(prompt) > 1500:
            return JsonResponse({
                'success': False,
                'error': 'Text must be less than 1500 characters'
            }, status=400)
        
        # Get optional parameters
        avatar_id = data.get('avatar_id', None)
        voice_id = data.get('voice_id', None)
        
        # Get API key from environment
        api_key = os.getenv('HEYGEN_API_KEY')
        
        if not api_key:
            logger.error("HEYGEN_API_KEY not found in environment")
            return JsonResponse({
                'success': False,
                'error': 'API key not configured. Add HEYGEN_API_KEY to your .env file'
            }, status=500)
        
        logger.info(f"Using API key: {api_key[:10]}...")
        
        # Initialize HeyGen API client
        client = HeyGenAPIClient(api_key)
        
        logger.info(f"Generating video with text: {prompt[:100]}...")
        
        # Start video generation
        generation_result = client.generate_video(
            text=prompt,
            avatar_id=avatar_id,
            voice_id=voice_id
        )
        
        # Get video_id from response
        video_id = generation_result.get('data', {}).get('video_id')
        if not video_id:
            logger.error(f"No video_id in response: {generation_result}")
            return JsonResponse({
                'success': False,
                'error': 'No video ID received from API'
            }, status=500)
        
        logger.info(f"Video generation started with video_id: {video_id}")
        
        # Wait for completion
        result = client.wait_for_completion(video_id, max_wait=300, poll_interval=5)
        
        if result['success']:
            logger.info(f"Video generated successfully: {result['video_url']}")
            return JsonResponse({
                'success': True,
                'video_url': result['video_url'],
                'thumbnail_url': result.get('thumbnail_url'),
                'duration': result.get('duration'),
                'video_id': video_id
            })
        else:
            logger.error(f"Video generation failed: {result['error']}")
            return JsonResponse({
                'success': False,
                'error': result['error'],
                'video_id': video_id
            }, status=500)
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def list_avatars(request):
    """Get list of available avatars"""
    try:
        api_key = os.getenv('HEYGEN_API_KEY')
        if not api_key:
            return JsonResponse({
                'success': False,
                'error': 'API key not configured'
            }, status=500)
        
        client = HeyGenAPIClient(api_key)
        result = client.list_avatars()
        
        if result and result.get('error') is None:
            return JsonResponse({
                'success': True,
                'avatars': result.get('data', {}).get('avatars', [])
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to fetch avatars'
            }, status=500)
    
    except Exception as e:
        logger.error(f"Error listing avatars: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def list_voices(request):
    """Get list of available voices"""
    try:
        api_key = os.getenv('HEYGEN_API_KEY')
        if not api_key:
            return JsonResponse({
                'success': False,
                'error': 'API key not configured'
            }, status=500)
        
        client = HeyGenAPIClient(api_key)
        result = client.list_voices()
        
        if result and result.get('error') is None:
            return JsonResponse({
                'success': True,
                'voices': result.get('data', {}).get('voices', [])
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to fetch voices'
            }, status=500)
    
    except Exception as e:
        logger.error(f"Error listing voices: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def test_api(request):
    """Test HeyGen API connection"""
    try:
        api_key = os.getenv('HEYGEN_API_KEY')
        
        if not api_key:
            return JsonResponse({
                'success': False,
                'error': 'API key not found in environment'
            })
        
        client = HeyGenAPIClient(api_key)
        result = client.list_avatars()
        
        if result and result.get('error') is None:
            return JsonResponse({
                'success': True,
                'message': 'API connection successful!',
                'avatar_count': len(result.get('data', {}).get('avatars', []))
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'API connection failed',
                'details': result
            })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })