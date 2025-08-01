"""Bytes economy commands for the Discord bot.

This module implements all bytes-related slash commands using the service layer
for business logic. Commands include balance checking, transfers, leaderboards,
and transaction history.
"""

from __future__ import annotations

import hikari
import lightbulb
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

# Import Discord embed functions needed for fallbacks
from smarter_dev.bot.utils.embeds import create_transaction_history_embed, create_leaderboard_embed
from smarter_dev.bot.utils.image_embeds import get_generator
from smarter_dev.bot.services.exceptions import (
    AlreadyClaimedError,
    InsufficientBalanceError,
    ServiceError,
    ValidationError
)

if TYPE_CHECKING:
    from smarter_dev.bot.services.bytes_service import BytesService

logger = logging.getLogger(__name__)

# Create plugin
plugin = lightbulb.Plugin("bytes")


@plugin.command
@lightbulb.command("bytes", "Bytes economy commands")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def bytes_group(ctx: lightbulb.Context) -> None:
    """Base bytes command group."""
    pass


@bytes_group.child
@lightbulb.command("balance", "Check your current bytes balance")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def balance_command(ctx: lightbulb.Context) -> None:
    """Handle balance command - shows current balance without auto-claiming."""
    
    service: BytesService = getattr(ctx.bot, 'd', {}).get('bytes_service')
    if not service:
        # Fallback to _services dict
        service = getattr(ctx.bot, 'd', {}).get('_services', {}).get('bytes_service')
    
    if not service:
        generator = get_generator()
        image_file = generator.create_error_embed("Bot services are not initialized. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    try:
        # Get current balance (defaults to fresh data)
        balance = await service.get_balance(str(ctx.guild_id), str(ctx.user.id))
        
        # Create enhanced balance embed
        generator = get_generator()
        
        # Format last daily as readable string
        last_daily_str = None
        if balance.last_daily:
            last_daily_str = balance.last_daily.strftime('%B %d, %Y')
        
        # Get username for display
        username = ctx.user.display_name or ctx.user.username
        
        image_file = generator.create_balance_embed(
            username=username,
            balance=balance.balance,
            streak_count=balance.streak_count,
            last_daily=last_daily_str,
            total_received=balance.total_received,
            total_sent=balance.total_sent
        )
        
        # Create share view with balance data
        from smarter_dev.bot.views.balance_views import BalanceShareView
        share_view = BalanceShareView(
            username=username,
            balance=balance.balance,
            streak_count=balance.streak_count,
            last_daily=last_daily_str,
            total_received=balance.total_received,
            total_sent=balance.total_sent
        )
        
        await ctx.respond(
            attachment=image_file,
            components=share_view.build_components(),
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return
            
    except ServiceError as e:
        logger.error(f"Service error in balance command: {e}")
        # Try to respond with error, but handle if already responded
        try:
            generator = get_generator()
            image_file = generator.create_error_embed("Failed to retrieve balance. Please try again later.")
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        except:
            pass  # Interaction was already responded to
        return
    except Exception as e:
        logger.exception(f"Unexpected error in balance command: {e}")
        # Try to respond with error, but handle if already responded
        try:
            generator = get_generator()
            image_file = generator.create_error_embed("An unexpected error occurred. Please try again later.")
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        except:
            pass  # Interaction was already responded to
        return



@bytes_group.child
@lightbulb.option("reason", "Reason for sending bytes", required=False)
@lightbulb.option("amount", "Amount to send", type=int)
@lightbulb.option("user", "User to send bytes to", type=hikari.User)
@lightbulb.command("send", "Send bytes to another user")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def send_command(ctx: lightbulb.Context) -> None:
    """Handle send command - transfer bytes between users."""
    service: BytesService = getattr(ctx.bot, 'd', {}).get('bytes_service')
    if not service:
        # Fallback to _services dict
        service = getattr(ctx.bot, 'd', {}).get('_services', {}).get('bytes_service')
    
    if not service:
        generator = get_generator()
        image_file = generator.create_error_embed("Bot services are not initialized. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    user = ctx.options.user
    amount = ctx.options.amount
    reason = ctx.options.reason
    
    # Validate amount
    if amount < 1 or amount > 10000:
        generator = get_generator()
        image_file = generator.create_error_embed("Amount must be between 1 and 10,000 bytes.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    # Validate receiver is in guild
    try:
        member = ctx.get_guild().get_member(user.id)
        if not member:
            generator = get_generator()
            image_file = generator.create_error_embed("That user is not in this server!")
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
            return
        
        # Prevent self-transfer (additional validation)
        if user.id == ctx.user.id:
            generator = get_generator()
            image_file = generator.create_error_embed("You can't send bytes to yourself!")
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
            return
        
        # Process transfer using service
        result = await service.transfer_bytes(
            str(ctx.guild_id),
            ctx.user,  # giver (UserProtocol)
            user,  # receiver (UserProtocol) 
            amount,
            reason
        )
        
        if not result.success:
            logger.info(f"Transfer failed: {result.reason}, is_cooldown_error: {result.is_cooldown_error}")
            generator = get_generator()
            # Use special cooldown embed for cooldown errors
            if result.is_cooldown_error:
                logger.info("Creating cooldown image embed")
                image_file = generator.create_cooldown_embed(result.reason, result.cooldown_end_timestamp)
            else:
                # Use error embed for transfer limit and other errors
                logger.info("Creating error image embed")
                image_file = generator.create_error_embed(result.reason)
            logger.info(f"Created image file: {type(image_file)}")
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
            return
        
        # Success image embed
        generator = get_generator()
        
        # Get sender's display name (nickname if set, otherwise username)
        try:
            sender_member = ctx.get_guild().get_member(ctx.user.id)
            sender_display_name = sender_member.display_name if sender_member else ctx.user.username
        except:
            sender_display_name = ctx.user.username
        
        # Get receiver's display name (nickname if set, otherwise username)
        try:
            receiver_member = ctx.get_guild().get_member(user.id)
            receiver_display_name = receiver_member.display_name if receiver_member else user.username
        except:
            receiver_display_name = user.username
        
        description = f"{sender_display_name} sent {amount:,} bytes to {receiver_display_name}"
        
        # Add reason if provided with 32px spacing (handled by image generator)
        if reason:
            description += f"\n\n{reason}"
        
        image_file = generator.create_success_embed("BYTES SENT", description)
        await ctx.respond(attachment=image_file)
        
    except InsufficientBalanceError as e:
        generator = get_generator()
        image_file = generator.create_error_embed(f"Insufficient balance! You need {e.required:,} bytes but only have {e.available:,}.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    except ValidationError as e:
        generator = get_generator()
        image_file = generator.create_error_embed(f"Invalid input: {e.message}")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    except ServiceError as e:
        logger.error(f"Service error in send command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("Transfer failed. Please try again later.")
        try:
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        except hikari.BadRequestError as discord_err:
            if "already been acknowledged" in str(discord_err):
                logger.warning("Interaction already acknowledged, skipping response")
            else:
                logger.error(f"Discord API error: {discord_err}")
        return
    except hikari.BadRequestError as e:
        if "already been acknowledged" in str(e):
            logger.warning("Interaction already acknowledged during transfer, skipping error response")
        else:
            logger.error(f"Discord interaction error in send command: {e}")
        return
    except Exception as e:
        logger.exception(f"Unexpected error in send command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("An unexpected error occurred. Please try again later.")
        try:
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        except hikari.BadRequestError as discord_err:
            if "already been acknowledged" in str(discord_err):
                logger.warning("Interaction already acknowledged, skipping error response")
            else:
                logger.error(f"Discord API error during error handling: {discord_err}")
        return


@bytes_group.child
@lightbulb.option("limit", "Number of users to show (1-25)", type=int, required=False)
@lightbulb.command("leaderboard", "View the guild bytes leaderboard")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def leaderboard_command(ctx: lightbulb.Context) -> None:
    """Handle leaderboard command - show top users by balance."""
    
    service: BytesService = getattr(ctx.bot, 'd', {}).get('bytes_service')
    if not service:
        # Fallback to _services dict
        service = getattr(ctx.bot, 'd', {}).get('_services', {}).get('bytes_service')
    
    if not service:
        generator = get_generator()
        image_file = generator.create_error_embed("Bot services are not initialized. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    limit = ctx.options.limit or 10
    if limit < 1 or limit > 25:
        limit = 10
    
    try:
        entries = await service.get_leaderboard(str(ctx.guild_id), limit)
        
        # Create user display names mapping
        user_display_names = {}
        for entry in entries:
            try:
                member = ctx.get_guild().get_member(int(entry.user_id))
                user_display_names[entry.user_id] = member.display_name if member else f"User {entry.user_id[:8]}"
            except:
                user_display_names[entry.user_id] = f"User {entry.user_id[:8]}"
        
        # Use image embed for 10 or fewer users, Discord embed for more
        if limit <= 10:
            generator = get_generator()
            image_file = generator.create_leaderboard_embed(entries, ctx.get_guild().name, user_display_names)
            
            # Create share view with leaderboard data
            from smarter_dev.bot.views.leaderboard_views import LeaderboardShareView
            share_view = LeaderboardShareView(
                entries=entries,
                guild_name=ctx.get_guild().name,
                user_display_names=user_display_names
            )
            
            await ctx.respond(
                attachment=image_file,
                components=share_view.build_components(),
                flags=hikari.MessageFlag.EPHEMERAL
            )
        else:
            # Use standard Discord embed for larger lists
            embed = create_leaderboard_embed(entries, ctx.get_guild().name, user_display_names)
            await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
        
    except ServiceError as e:
        logger.error(f"Service error in leaderboard command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("Failed to get leaderboard. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
    except Exception as e:
        logger.exception(f"Unexpected error in leaderboard command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("An unexpected error occurred. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)


@bytes_group.child
@lightbulb.option("limit", "Number of transactions to show (1-20)", type=int, required=False)
@lightbulb.command("history", "View your recent bytes transactions")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def history_command(ctx: lightbulb.Context) -> None:
    """Handle history command - show user's transaction history."""
    service: BytesService = getattr(ctx.bot, 'd', {}).get('bytes_service')
    if not service:
        # Fallback to _services dict
        service = getattr(ctx.bot, 'd', {}).get('_services', {}).get('bytes_service')
    
    if not service:
        generator = get_generator()
        image_file = generator.create_error_embed("Bot services are not initialized. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    limit = ctx.options.limit or 10
    if limit < 1 or limit > 20:
        limit = 10
    
    try:
        transactions = await service.get_transaction_history(
            str(ctx.guild_id),
            user_id=str(ctx.user.id),
            limit=limit
        )
        
        # Use image embed for 10 or fewer transactions, Discord embed for more
        if limit <= 10:
            generator = get_generator()
            image_file = generator.create_history_embed(transactions, str(ctx.user.id))
            
            # Create share view with history data
            from smarter_dev.bot.views.history_views import HistoryShareView
            share_view = HistoryShareView(
                transactions=transactions,
                user_id=str(ctx.user.id)
            )
            
            await ctx.respond(
                attachment=image_file,
                components=share_view.build_components(),
                flags=hikari.MessageFlag.EPHEMERAL
            )
        else:
            # Use standard Discord embed for larger lists
            embed = create_transaction_history_embed(transactions, str(ctx.user.id))
            await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
        
    except ServiceError as e:
        logger.error(f"Service error in history command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("Failed to get transaction history. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
    except Exception as e:
        logger.exception(f"Unexpected error in history command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("An unexpected error occurred. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)


@bytes_group.child
@lightbulb.command("info", "View the current bytes economy settings for this server")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def info_command(ctx: lightbulb.Context) -> None:
    """Handle info command - show guild bytes configuration."""
    service: BytesService = getattr(ctx.bot, 'd', {}).get('bytes_service')
    if not service:
        # Fallback to _services dict
        service = getattr(ctx.bot, 'd', {}).get('_services', {}).get('bytes_service')
    
    if not service:
        generator = get_generator()
        image_file = generator.create_error_embed("Bot services are not initialized. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    try:
        config = await service.get_config(str(ctx.guild_id))
        
        generator = get_generator()
        image_file = generator.create_config_embed(config, ctx.get_guild().name)
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        
    except ServiceError as e:
        logger.error(f"Service error in config command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("Failed to get configuration. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
    except Exception as e:
        logger.exception(f"Unexpected error in config command: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("An unexpected error occurred. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)


@plugin.command
@lightbulb.command("Send Bytes", "Send bytes to the author of this message")
@lightbulb.implements(lightbulb.MessageCommand)
async def send_bytes_context_menu(ctx: lightbulb.Context) -> None:
    """Handle message context menu for sending bytes to message author."""
    service: BytesService = getattr(ctx.bot, 'd', {}).get('bytes_service')
    if not service:
        # Fallback to _services dict
        service = getattr(ctx.bot, 'd', {}).get('_services', {}).get('bytes_service')
    
    if not service:
        generator = get_generator()
        image_file = generator.create_error_embed("Bot services are not initialized. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    # Get the target message and its author
    target_message = ctx.options.target
    recipient = target_message.author
    
    # Prevent sending bytes to bots
    if recipient.is_bot:
        generator = get_generator()
        image_file = generator.create_error_embed("You cannot send bytes to bots!")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    # Prevent self-transfer
    if recipient.id == ctx.user.id:
        generator = get_generator()
        image_file = generator.create_error_embed("You cannot send bytes to yourself!")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    # Validate recipient is in guild
    try:
        member = ctx.get_guild().get_member(recipient.id)
        if not member:
            generator = get_generator()
            image_file = generator.create_error_embed("That user is not in this server!")
            await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
            return
    except Exception:
        generator = get_generator()
        image_file = generator.create_error_embed("Unable to verify user membership in this server.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    # Get guild config for max transfer limit
    try:
        config = await service.get_config(str(ctx.guild_id))
        max_transfer = config.max_transfer
    except Exception as e:
        logger.error(f"Failed to get guild config for transfer limit: {e}")
        generator = get_generator()
        image_file = generator.create_error_embed("Failed to get server configuration. Please try again later.")
        await ctx.respond(attachment=image_file, flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    # Create and show modal for amount/reason input
    from smarter_dev.bot.views.bytes_views import create_send_bytes_modal, SendBytesModalHandler
    
    modal = create_send_bytes_modal(recipient, max_transfer)
    
    # Store the modal handler for the interaction
    handler = SendBytesModalHandler(
        recipient=recipient,
        guild_id=str(ctx.guild_id),
        giver=ctx.user,
        max_transfer=max_transfer,
        bytes_service=service,
        target_message_id=target_message.id
    )
    
    # Store handler in bot data for later retrieval
    if not hasattr(ctx.bot, 'd'):
        ctx.bot.d = {}
    if 'modal_handlers' not in ctx.bot.d:
        ctx.bot.d['modal_handlers'] = {}
    
    handler_key = f"send_bytes_modal:{recipient.id}:{ctx.user.id}"
    ctx.bot.d['modal_handlers'][handler_key] = handler
    
    await ctx.respond_with_modal(
        modal.title,
        modal.custom_id,
        components=modal.components
    )


def load(bot: lightbulb.BotApp) -> None:
    """Load the bytes plugin."""
    bot.add_plugin(plugin)
    logger.info("Bytes plugin loaded")


def unload(bot: lightbulb.BotApp) -> None:
    """Unload the bytes plugin."""
    bot.remove_plugin(plugin)
    logger.info("Bytes plugin unloaded")