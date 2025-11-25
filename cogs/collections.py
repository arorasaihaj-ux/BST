import discord
from discord.ext import commands
from discord import app_commands
import config
from database import db

class Collections(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="collections", description="View item collections")
    async def view_collections(self, interaction: discord.Interaction):
        """View all collections"""
        try:
            async with db.pool.acquire() as conn:
                collections = await conn.fetch("""
                    SELECT c.*, 
                           uc.completed,
                           uc.completed_at
                    FROM collections c
                    LEFT JOIN user_collections uc ON c.collection_id = uc.collection_id 
                        AND uc.user_id = $1
                    ORDER BY c.collection_id
                """, interaction.user.id)
            
            if not collections:
                await interaction.response.send_message(
                    "No collections available.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(color=config.Colors.PRIMARY)
            
            header = config.Design.header("ITEM COLLECTIONS", 28)
            embed.description = f"\n{header}\n"
            
            completed_count = sum(1 for c in collections if c['completed'])
            total_count = len(collections)
            completion_rate = (completed_count / total_count) * 100
            
            embed.add_field(
                name="Progress",
                value=f"**{completed_count}/{total_count}** collections completed ({completion_rate:.1f}%)",
                inline=False
            )
            
            for collection in collections:
                status = "✅" if collection['completed'] else "⏳"
                
                # Get collection items and user progress
                collection_items = await conn.fetch("""
                    SELECT ci.*, i.name as item_name,
                           COALESCE(ui.quantity, 0) as user_quantity
                    FROM collection_items ci
                    JOIN items i ON ci.item_id = i.item_id
                    LEFT JOIN user_items ui ON ci.item_id = ui.item_id AND ui.user_id = $1
                    WHERE ci.collection_id = $2
                """, interaction.user.id, collection['collection_id'])
                
                items_text = ""
                for item in collection_items:
                    has_item = "✅" if item['user_quantity'] >= item['required_quantity'] else "❌"
                    items_text += f"{has_item} {item['item_name']} x{item['required_quantity']}\n"
                
                reward_text = f"Reward: {collection['reward_bst']} BST"
                if collection['reward_item_id']:
                    reward_item = await conn.fetchrow("SELECT name FROM items WHERE item_id = $1", collection['reward_item_id'])
                    reward_text += f" + {reward_item['name']}"
                
                embed.add_field(
                    name=f"{status} {collection['name']}",
                    value=f"{collection['description']}\n\n{items_text}\n{reward_text}",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="claimcollection", description="Claim collection reward")
    async def claim_collection(self, interaction: discord.Interaction, collection_id: str):
        """Claim collection reward"""
        try:
            async with db.pool.acquire() as conn:
                # Check if user has completed the collection
                user_collection = await conn.fetchrow("""
                    SELECT uc.*, c.reward_bst, c.reward_item_id
                    FROM user_collections uc
                    JOIN collections c ON uc.collection_id = c.collection_id
                    WHERE uc.user_id = $1 AND uc.collection_id = $2 AND uc.completed = true
                """, interaction.user.id, collection_id)
                
                if not user_collection:
                    await interaction.response.send_message(
                        "Collection not found or not completed.",
                        ephemeral=True
                    )
                    return
                
                if user_collection['reward_claimed']:
                    await interaction.response.send_message(
                        "Reward already claimed.",
                        ephemeral=True
                    )
                    return
                
                # Check if user still has all required items
                collection_items = await conn.fetch("""
                    SELECT ci.item_id, ci.required_quantity,
                           COALESCE(ui.quantity, 0) as user_quantity
                    FROM collection_items ci
                    LEFT JOIN user_items ui ON ci.item_id = ui.item_id AND ui.user_id = $1
                    WHERE ci.collection_id = $2
                """, interaction.user.id, collection_id)
                
                for item in collection_items:
                    if item['user_quantity'] < item['required_quantity']:
                        await interaction.response.send_message(
                            "You no longer have all the required items for this collection.",
                            ephemeral=True
                        )
                        return
                
                # Award rewards
                if user_collection['reward_bst'] > 0:
                    await conn.execute("""
                        UPDATE users SET bst_balance = bst_balance + $1
                        WHERE user_id = $2
                    """, user_collection['reward_bst'], interaction.user.id)
                    
                    await conn.execute("""
                        INSERT INTO transactions (user_id, tx_type, amount_bst, metadata)
                        VALUES ($1, 'collection_reward', $2, $3)
                    """, interaction.user.id, user_collection['reward_bst'], {
                        "collection_id": collection_id
                    })
                
                if user_collection['reward_item_id']:
                    await conn.execute("""
                        INSERT INTO user_items (user_id, item_id, obtained_from)
                        VALUES ($1, $2, 'collection')
                        ON CONFLICT (user_id, item_id) DO UPDATE SET
                            quantity = user_items.quantity + 1
                    """, interaction.user.id, user_collection['reward_item_id'])
                
                # Remove collection items (optional - depends on design)
                # If you want to remove items after claiming, uncomment below:
                # for item in collection_items:
                #     await conn.execute("""
                #         UPDATE user_items SET quantity = quantity - $1
                #         WHERE user_id = $2 AND item_id = $3
                #     """, item['required_quantity'], interaction.user.id, item['item_id'])
                
                # Mark as claimed
                await conn.execute("""
                    UPDATE user_collections SET reward_claimed = true
                    WHERE user_id = $1 AND collection_id = $2
                """, interaction.user.id, collection_id)
                
                # Get collection name
                collection = await conn.fetchrow("""
                    SELECT name FROM collections WHERE collection_id = $1
                """, collection_id)
                
                embed = discord.Embed(
                    description=config.Design.small_caps(
                        f"claimed reward for {collection['name']} collection"
                    ),
                    color=config.Colors.SUCCESS
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True
            )

    async def check_collection_progress(self, user_id: int):
        """Check and update collection progress"""
        try:
            async with db.pool.acquire() as conn:
                collections = await conn.fetch("SELECT * FROM collections")
                
                for collection in collections:
                    # Skip if already completed
                    user_collection = await conn.fetchrow("""
                        SELECT * FROM user_collections 
                        WHERE user_id = $1 AND collection_id = $2 AND completed = true
                    """, user_id, collection['collection_id'])
                    
                    if user_collection:
                        continue
                    
                    # Get collection items and user progress
                    collection_items = await conn.fetch("""
                        SELECT ci.*, i.name as item_name,
                               COALESCE(ui.quantity, 0) as user_quantity
                        FROM collection_items ci
                        JOIN items i ON ci.item_id = i.item_id
                        LEFT JOIN user_items ui ON ci.item_id = ui.item_id AND ui.user_id = $1
                        WHERE ci.collection_id = $2
                    """, user_id, collection['collection_id'])
                    
                    # Check if all items are collected
                    all_collected = True
                    for item in collection_items:
                        if item['user_quantity'] < item['required_quantity']:
                            all_collected = False
                            break
                    
                    if all_collected:
                        # Mark collection as completed
                        existing = await conn.fetchrow("""
                            SELECT * FROM user_collections 
                            WHERE user_id = $1 AND collection_id = $2
                        """, user_id, collection['collection_id'])
                        
                        if existing:
                            await conn.execute("""
                                UPDATE user_collections 
                                SET completed = true, completed_at = $1
                                WHERE user_id = $2 AND collection_id = $3
                            """, discord.utils.utcnow(), user_id, collection['collection_id'])
                        else:
                            await conn.execute("""
                                INSERT INTO user_collections (user_id, collection_id, completed, completed_at)
                                VALUES ($1, $2, true, $3)
                            """, user_id, collection['collection_id'], discord.utils.utcnow())
                        
                        # Notify user
                        user = self.bot.get_user(user_id)
                        if user:
                            try:
                                embed = discord.Embed(
                                    description=config.Design.small_caps(
                                        f"collection completed: {collection['name']}"
                                    ),
                                    color=config.Colors.SUCCESS
                                )
                                await user.send(embed=embed)
                            except:
                                pass
                
        except Exception as e:
            print(f"Error checking collection progress: {e}")

    @commands.Cog.listener()
    async def on_user_item_update(self, user_id: int):
        """Check collections when user items change"""
        await self.check_collection_progress(user_id)

async def setup(bot):
    await bot.add_cog(Collections(bot))