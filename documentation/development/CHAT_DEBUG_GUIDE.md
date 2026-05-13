# Chat History Debugging & Testing Guide

## Issues Fixed

### 1. **Database DateTime Handling** 
- **Problem**: SQLAlchemy datetime defaults with lambdas weren't working properly
- **Fix**: Updated `database.py` to use a proper function reference `get_utc_now()` instead of lambda
- **Files**: `backend/database.py`

### 2. **Silent Error Handling**  
- **Problem**: Conversation errors were being silently swallowed, making debugging impossible
- **Fix**: Added console.error logging and error display in the chat UI
- **Files**: `frontend/src/App.jsx`

### 3. **Missing Error Clearing**
- **Problem**: Errors from previous operations weren't being cleared before new operations
- **Fix**: Added `setError('')` at the start of `createNewConversation()` and `loadConversation()`
- **Files**: `frontend/src/App.jsx`

### 4. **Error Display in Chat Section**
- **Problem**: Error messages weren't visible in the chat section
- **Fix**: Added error alert display at the top of the chat panel
- **Files**: `frontend/src/App.jsx`

### 5. **Missing refreshConversations in Dashboard**
- **Problem**: The refresh dashboard function didn't refresh conversations
- **Fix**: Added `refreshConversations()` call to `refreshDashboard()`
- **Files**: `frontend/src/App.jsx`

## Testing the API

### Method 1: Using the Test Script

```bash
cd /home/ashok/Desktop/RAGSYSTEM
bash test_chat_api.sh
```

This will test all conversation endpoints.

### Method 2: Manual Testing with curl

#### 1. Create a new conversation
```bash
curl -X POST http://localhost:5200/conversations \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My Test Conversation",
    "knowledge_base": "default"
  }'
```

Expected response:
```json
{
  "status": "created",
  "conversation": {
    "id": "uuid-here",
    "title": "My Test Conversation",
    "knowledge_base": "default",
    "created_at": "2026-05-06T...",
    "updated_at": "2026-05-06T...",
    "message_count": 0
  }
}
```

#### 2. List all conversations
```bash
curl -X GET "http://localhost:5200/conversations?knowledge_base=default"
```

Expected response:
```json
{
  "status": "success",
  "conversations": [...]
}
```

#### 3. Get specific conversation with messages
```bash
curl -X GET "http://localhost:5200/conversations/{conversation_id}"
```

#### 4. Update conversation title
```bash
curl -X PUT "http://localhost:5200/conversations/{conversation_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title"
  }'
```

#### 5. Delete conversation
```bash
curl -X DELETE "http://localhost:5200/conversations/{conversation_id}"
```

## Frontend Testing Checklist

- [ ] Backend is running (`python -m app` in backend folder)
- [ ] Frontend is running (if not running together)
- [ ] Database is running (PostgreSQL at localhost:5202)
- [ ] Open browser dev console (F12) to check for errors
- [ ] Click "+ New Chat" button - should create and display a new conversation
- [ ] Check browser console for any error messages
- [ ] Look for error alert in the chat section if something fails
- [ ] Try asking a question in the new conversation
- [ ] Click on another conversation in the list to switch
- [ ] Try deleting a conversation

## Browser Console Debugging

If something isn't working:

1. **Open Developer Console** (F12)
2. **Check Console tab** for error messages (especially from `refreshConversations`)
3. **Check Network tab** to see API requests and responses
4. **Look for errors like**:
   - 404 (endpoint doesn't exist)
   - 500 (server error)
   - CORS errors (should not happen with current setup)

## Common Issues & Solutions

### Issue: "No conversations yet" message stays after clicking "+ New Chat"

**Possible causes:**
1. Backend service not running
2. Database not running  
3. API endpoint returning error (check console)
4. Database tables not created

**Solution:**
- Ensure `init_db()` is being called on backend startup
- Check database connection string in `.env`
- Check console for specific error messages

### Issue: Conversations load but conversation doesn't open when clicked

**Possible causes:**
1. `loadConversation()` failing silently  
2. Async timing issue
3. API returning invalid data

**Solution:**
- Check browser console for error logs
- Verify API response structure matches expected format
- Check that conversation ID is being passed correctly

### Issue: Database errors like "table conversations does not exist"

**Solution:**
1. Make sure backend is restarted after changes
2. Check that `init_db()` is called
3. You can manually create tables by running:
   ```python
   from backend.database import init_db
   init_db()
   ```

## Logs to Check

### Backend Logs
- Look for any SQL errors in backend terminal
- Check for `Exception` stack traces

### Frontend Logs  
- Browser Console (F12)
- Network tab shows failed API calls
- React DevTools extension can help inspect state

## Quick Restart Procedure

1. **Stop backend**:
   ```bash
   cd /home/ashok/Desktop/RAGSYSTEM/medical-rag
   bash stop.sh
   ```

2. **Make sure database is running**:
   ```bash
   # If using Docker
   docker ps | grep postgres
   
   # Or check if it's running directly
   ```

3. **Start backend**:
   ```bash
   cd /home/ashok/Desktop/RAGSYSTEM/med ical-rag
   source ../.venv/bin/activate
   python -m backend.app
   ```

4. **Refresh browser**
   - Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
   - Clear any cached data if needed

## Next Steps if Still Having Issues

1. Check the API directly with curl first
2. Verify database connection
3. Look at backend logs for specific errors
4. Check browser console for client-side errors
5. Ensure all files were modified correctly:
   - `backend/database.py` - New file with models
   - `backend/app.py` - Updated imports and endpoints
   - `frontend/src/App.jsx` - Updated with conversation state and handlers
   - `frontend/src/App.css` - Updated with chat styling
