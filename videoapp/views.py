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





class HygenAPIClient:
    """
    Hygen API client for text-to-video generation
    """
    def __init__(self, api_key: str):
        self.api_key = os.getenv('HYGEN_API_KEY')
        self.base_url = "https://api.hygen.ai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def generate_video(self, prompt: str, duration: int = 5, 
                      aspect_ratio: str = "16:9", 
                      style: str = None) -> dict:
        """
        Initiate video generation
        """
        endpoint = f"{self.base_url}/generate"
        
        payload = {
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio
        }
        
        if style:
            payload["style"] = style
        
        try:
            response = requests.post(
                endpoint, 
                json=payload, 
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating video: {e}")
            raise Exception(f"Failed to generate video: {str(e)}")
    
    def check_status(self, task_id: str) -> dict:
        """
        Check video generation status
        """
        endpoint = f"{self.base_url}/status/{task_id}"
        
        try:
            response = requests.get(
                endpoint, 
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking status: {e}")
            raise Exception(f"Failed to check status: {str(e)}")
    
    def wait_for_completion(self, task_id: str, max_wait: int = 300, 
                          poll_interval: int = 5) -> dict:
        """
        Wait for video generation to complete
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status = self.check_status(task_id)
            
            state = status.get('status')
            
            if state == 'completed':
                return {
                    'success': True,
                    'video_url': status.get('video_url'),
                    'status': state
                }
            elif state == 'failed':
                return {
                    'success': False,
                    'error': status.get('error', 'Video generation failed'),
                    'status': state
                }
            
            # Still processing
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
    Django view to handle video generation requests
    
    Expected JSON payload:
    {
        "prompt": "Video description",
        "duration": 5,
        "aspect_ratio": "16:9",
        "style": "cinematic" (optional)
    }
    
    Returns JSON response:
    {
        "success": true/false,
        "video_url": "url to video" (if successful),
        "error": "error message" (if failed),
        "task_id": "task identifier"
    }
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        
        # Validate required fields
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({
                'success': False,
                'error': 'Prompt is required'
            }, status=400)
        
        # Get optional parameters with defaults
        duration = data.get('duration', 5)
        aspect_ratio = data.get('aspect_ratio', '16:9')
        style = data.get('style', None)
        
        # Validate duration
        if not isinstance(duration, int) or duration < 3 or duration > 10:
            return JsonResponse({
                'success': False,
                'error': 'Duration must be between 3 and 10 seconds'
            }, status=400)
        
        # Validate aspect ratio
        valid_ratios = ['16:9', '9:16', '1:1', '4:3']
        if aspect_ratio not in valid_ratios:
            return JsonResponse({
                'success': False,
                'error': f'Invalid aspect ratio. Must be one of: {", ".join(valid_ratios)}'
            }, status=400)
        
        # Get API key from settings
        api_key = os.getenv('HYGEN_API_KEY')
        if not api_key:
            logger.error("HYGEN_API_KEY not configured in settings")
            return JsonResponse({
                'success': False,
                'error': 'API key not configured'
            }, status=500)
        
        # Initialize Hygen API client
        client = HygenAPIClient(api_key)
        
        logger.info(f"Generating video with prompt: {prompt}")
        
        # Start video generation
        generation_result = client.generate_video(
            prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            style=style
        )
        
        task_id = generation_result.get('task_id')
        if not task_id:
            return JsonResponse({
                'success': False,
                'error': 'No task ID received from API'
            }, status=500)
        
        logger.info(f"Video generation started with task_id: {task_id}")
        
        # Wait for completion (with timeout)
        result = client.wait_for_completion(task_id, max_wait=300, poll_interval=5)
        
        if result['success']:
            logger.info(f"Video generated successfully: {result['video_url']}")
            return JsonResponse({
                'success': True,
                'video_url': result['video_url'],
                'task_id': task_id
            })
        else:
            logger.error(f"Video generation failed: {result['error']}")
            return JsonResponse({
                'success': False,
                'error': result['error'],
                'task_id': task_id
            }, status=500)
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    
    except Exception as e:
        logger.error(f"Unexpected error in generate_video: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def generate_video_async(request):
    """
    Start video generation asynchronously (returns task_id immediately)
    Use this if you want to implement polling from the frontend
    """
    try:
        data = json.loads(request.body)
        
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({
                'success': False,
                'error': 'Prompt is required'
            }, status=400)
        
        duration = data.get('duration', 5)
        aspect_ratio = data.get('aspect_ratio', '16:9')
        style = data.get('style', None)
        
        # Get API key
        api_key = os.getenv('HYGEN_API_KEY')
        if not api_key:
            return JsonResponse({
                'success': False,
                'error': 'API key not configured'
            }, status=500)
        
        # Initialize client and start generation
        client = HygenAPIClient(api_key)
        result = client.generate_video(
            prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            style=style
        )
        
        task_id = result.get('task_id')
        
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'message': 'Video generation started'
        })
    
    except Exception as e:
        logger.error(f"Error starting video generation: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def check_video_status(request, task_id):
    """
    Check status of video generation
    Use with async approach
    
    URL: /check-video-status/<task_id>/
    """
    try:
        api_key = os.getenv('HYGEN_API_KEY')
        if not api_key:
            return JsonResponse({
                'success': False,
                'error': 'API key not configured'
            }, status=500)
        
        client = HygenAPIClient(api_key)
        status = client.check_status(task_id)
        
        state = status.get('status')
        
        if state == 'completed':
            return JsonResponse({
                'success': True,
                'status': 'completed',
                'video_url': status.get('video_url')
            })
        elif state == 'failed':
            return JsonResponse({
                'success': False,
                'status': 'failed',
                'error': status.get('error', 'Generation failed')
            })
        else:
            return JsonResponse({
                'success': True,
                'status': 'processing',
                'progress': status.get('progress', 0)
            })
    
    except Exception as e:
        logger.error(f"Error checking status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)