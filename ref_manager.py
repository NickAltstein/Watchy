# In your main FastAPI app, replace the ref_manager imports and usage:

# Old imports:
# from ref_manager import init_ref_table, update_target_price_in_db, get_all_targets_from_db

# New imports:
from ref_manager import RefManager

# In your settings class, add:
class Settings(BaseSettings):
    # ... existing settings ...
    REF_MANAGER_POOL_SIZE: int = 5

# During app initialization:
ref_manager = RefManager(settings.DATABASE_URL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize ref manager with pool
    await ref_manager.init_pool(
        minsize=1,
        maxsize=settings.REF_MANAGER_POOL_SIZE
    )
    await ref_manager.init_ref_table()
    
    # ... rest of initialization ...
    
    # Initial cache load
    initial_cache = await ref_manager.get_all_targets()
    TARGET_PRICES_CACHE.update(initial_cache)
    
    # ... rest of lifespan ...
    yield
    
    # Cleanup
    await ref_manager.close()
    # ... rest of cleanup ...

# Update the admin endpoint:
@app.post("/admin/update-target", tags=["admin"])
async def update_target(payload: TargetUpdatePayload):
    if payload.admin_secret != settings.ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    
    await ref_manager.update_target_price(
        payload.ref_number,
        payload.market_price
    )
    
    # Refresh cache
    new_cache = await ref_manager.get_all_targets()
    TARGET_PRICES_CACHE.update(new_cache)
    
    logger.info(f"Target price updated: {payload.ref_number} = {payload.market_price}")
    
    return {
        "status": "success",
        "ref": payload.ref_number,
        "price": payload.market_price,
        "cache_size": len(new_cache)
    }

# Add new admin endpoints:
@app.get("/admin/targets", tags=["admin"])
async def get_all_targets_admin(admin_secret: str):
    """Get all target prices with details (admin only)"""
    if admin_secret != settings.ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    
    targets = await ref_manager.get_targets_with_details()
    return {
        "targets": targets,
        "count": len(targets),
        "timestamp": datetime.now().isoformat()
    }

@app.delete("/admin/target/{ref_number}", tags=["admin"])
async def delete_target(ref_number: str, admin_secret: str):
    """Delete a target price (admin only)"""
    if admin_secret != settings.ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    
    deleted = await ref_manager.delete_target(ref_number)
    if deleted:
        # Refresh cache
        new_cache = await ref_manager.get_all_targets()
        TARGET_PRICES_CACHE.update(new_cache)
    
    return {
        "status": "deleted" if deleted else "not_found",
        "ref": ref_number,
        "cache_size": TARGET_PRICES_CACHE.size()
    }
