<?php

namespace FSPoster\App\Providers\Schedules;

use FSPoster\App\Models\Channel;
use FSPoster\App\Models\Planner;
use FSPoster\App\Models\Post;
use FSPoster\App\Models\Schedule;
use FSPoster\App\Providers\Channels\ChannelService;
use FSPoster\App\Providers\Channels\ChannelSessionException;
use FSPoster\App\Providers\Core\Settings;
use FSPoster\App\Providers\DB\Collection;
use FSPoster\App\Providers\DB\DB;
use FSPoster\App\Providers\Helpers\Date;
use FSPoster\App\Providers\Helpers\Helper;

class ScheduleService
{

    /**
     * @param Planner $planner
     * @param         $postId
     *
     * @return bool
     */
    public static function createSchedulesFromPlanner ( Collection $planner, $postId ): bool
    {
        $channelsIds = empty( $planner->channels ) ? [] : explode( ',', $planner->channels );

        if ( empty( $channelsIds ) )
            return false;

        $channels = Channel::where( 'id', 'in', $channelsIds )->fetchAll();

        if ( empty( $channels ) )
            return false;

		$plannerCustomizationData = json_decode( $planner->customization_data, true );
	    $scheduleGroupId = Helper::generateUUID();

        //How many seconds should be between shares to same social network
	    $sendTime = Date::dateTimeSQL();

	    $intervalEachPost = Settings::get( 'post_interval', 0 );
        $enablePostInterval = (int)Settings::get('enable_post_interval', 0);

        foreach ( $channels as $channel )
        {
            Schedule::insert( [
	            'blog_id'               => $planner->blog_id,
	            'wp_post_id'            => $postId,
	            'user_id'               => $planner->created_by,
	            'channel_id'            => $channel->id,
	            'planner_id'            => $planner->id,
	            'group_id'              => $scheduleGroupId,
	            'status'                => 'not_sent',
	            'send_time'             => $sendTime,
	            'customization_data'    => json_encode( $plannerCustomizationData[$channel->id] ?? [] ),
            ] );

	        if ( $intervalEachPost > 0  && $enablePostInterval !== 0)
		        $sendTime = Date::dateTimeSQL( $sendTime, '+' . $intervalEachPost . ' seconds' );
        }

        return true;
    }

    public static function createSchedulesFromWpPost ( $wpPostId, $scheduleGroupId = '', $schedulesData = [], $shareAt = null )
    {
	    $wpPostInfo = \WP_Post::get_instance( $wpPostId );

		if ( $wpPostInfo->post_status === 'trash' )
			return '';

	    if ( empty( $scheduleGroupId ) )
            $scheduleGroupId = Helper::generateUUID();


        if ( empty( $schedulesData ) )
            $schedulesData = self::getDefaultSchedulesPostData( $wpPostId );

		if( is_null( $shareAt ) ) {
	        $sendTime = Date::dateTimeSQL( Date::epoch() > Date::epoch($wpPostInfo->post_date) ? 'now' : $wpPostInfo->post_date, '+10 seconds' );

            $delay = (int)Settings::get( 'auto_share_delay', 0 );
            if ( $delay > 0 )
                $sendTime = Date::dateTimeSQL( $sendTime, '+' . $delay . ' seconds' );
        }
		else
            $sendTime = Date::dateTimeSQL( $shareAt );

        $intervalEachPost = Settings::get('post_interval', 0);
        $enablePostInterval = (int)Settings::get('enable_post_interval', 0);

        $scheduleStatus = self::getScheduleStatusByWpPostStatus( $wpPostInfo->post_status );

        foreach ( $schedulesData as $schedule )
        {
            Schedule::insert( [
                'blog_id'            => Helper::getBlogId(),
                'wp_post_id'         => $wpPostId,
                'user_id'            => get_current_user_id(),
                'channel_id'         => $schedule[ 'channel_id' ],
                'group_id'           => $scheduleGroupId,
                'send_time'          => $sendTime,
                'status'             => $scheduleStatus,
                'customization_data' => json_encode( $schedule[ 'custom_post_data' ] ),
            ] );

            if ( $intervalEachPost > 0 && $enablePostInterval !== 0 )
                $sendTime = Date::dateTimeSQL( $sendTime, '+' . $intervalEachPost . ' seconds' );
        }

        return $scheduleGroupId;
    }

	public static function getDefaultSchedulesPostData ( int $wpPostId ): array
	{
		$wpPost = \WP_Post::get_instance( $wpPostId );

		if ( empty( $wpPost ) )
			return [];

		// if post created by FS Poster (calendar), then this hook is not needed
		if ( $wpPost->post_type === 'fsp_post' )
			return [];

		// if post type is not whitelisted, just skip
		if ( !in_array( $wpPost->post_type, Settings::get( 'allowed_post_types', [ 'post', 'page', 'attachment', 'product' ] ) ) )
			return [];

		$data = [];
		$activeChannels = ChannelService::getActiveChannelsToAutoShare( $wpPostId );

		foreach ( $activeChannels as $channel )
		{
			$channelSession = $channel->channel_session->select( 'social_network' )->fetch();

            if ( empty( $channelSession ) )
            {
                continue;
            }

			$data[] = [
				'channel_id'       => $channel->id,
				'custom_post_data' => apply_filters( 'fsp_channel_custom_post_data', [], $channel, $channelSession->social_network ),
			];
		}

		return $data;
	}

	public static function getScheduleStatusByWpPostStatus ( $wpPostStatus ): string
    {
        if ( $wpPostStatus === 'trash' ) {
            return 'trash';
        }

        if ( $wpPostStatus === 'auto-draft' ) {
            return 'auto-draft';
        }

		return in_array( $wpPostStatus, ['draft', 'pending'] ) ? 'draft' : 'not_sent';
	}

	public static function updateSchedulesStatusAndDeteFromWpPost ( $wpPostId, $scheduleGroupId )
	{
		$wpPostInfo = \WP_Post::get_instance( $wpPostId );

		$schedulesNewStatus = self::getScheduleStatusByWpPostStatus( $wpPostInfo->post_status );

		$sendTime = Date::dateTimeSQL( Date::epoch() > Date::epoch($wpPostInfo->post_date) ? 'now' : $wpPostInfo->post_date, '+10 seconds' );

		$delay = (int)Settings::get( 'auto_share_delay', 0 );
		if ( $delay > 0 )
			$sendTime = Date::dateTimeSQL( $sendTime, '+' . $delay . ' seconds' );

		$intervalEachPost = Settings::get( 'post_interval', 0 );
        $enablePostInterval = (int)Settings::get('enable_post_interval', 0);

		$allSchedules = Schedule::where( 'wp_post_id', $wpPostId )
		                        ->where( 'group_id', $scheduleGroupId )
		                        ->fetchAll();

		foreach ( $allSchedules AS $scheduleInf )
		{
			Schedule::where('id', $scheduleInf->id)->update([
		        'status'    =>  $schedulesNewStatus,
		        'send_time' =>  $sendTime,
	        ]);

			if ( $intervalEachPost > 0  && $enablePostInterval !== 0)
				$sendTime = Date::dateTimeSQL( $sendTime, '+' . $intervalEachPost . ' seconds' );
		}

		return true;
	}

	public static function enableAutoShareForWpPost ( $wpPostId )
	{
		if( metadata_exists( 'post', $wpPostId, 'fsp_runned_for_this_post' ) )
			return;

		update_post_meta( $wpPostId, 'fsp_enable_auto_share', true );

		$scheduleGroupId = get_post_meta( $wpPostId, 'fsp_schedule_group_id', true );

		if( ! empty( $scheduleGroupId ) )
			self::restoreScheduleCacheDataForWpPost ( $wpPostId, $scheduleGroupId );
	}

	public static function disableAutoShareForWpPost ( $wpPostId )
	{
		if( metadata_exists( 'post', $wpPostId, 'fsp_runned_for_this_post' ) )
			return;

		update_post_meta( $wpPostId, 'fsp_enable_auto_share', false );

		$scheduleGroupId = get_post_meta( $wpPostId, 'fsp_schedule_group_id', true );

		if( ! empty( $scheduleGroupId ) && get_post_meta( $wpPostId, 'fsp_schedule_created_manually', true ) )
			self::saveScheduleCacheDataForWpPost( $wpPostId, $scheduleGroupId );

		self::deleteSchedulesFromWpPost( $wpPostId, $scheduleGroupId );
	}

	public static function saveScheduleCacheDataForWpPost ( $wpPostId, $scheduleGroupId )
	{
		$existingSchedules = Schedule::where( 'wp_post_id', $wpPostId )
		                             ->where( 'group_id', $scheduleGroupId )
		                             ->fetchAll();

		foreach ( $existingSchedules as $schedule )
		{
			$data[] = [
				'channel_id'       => $schedule->channel_id,
				'custom_post_data' => json_decode( $schedule->customization_data, true ),
			];
		}

		update_post_meta( $wpPostId, 'fsp_cache_schedules_data', $data );
	}

	public static function deleteScheduleCacheDataForWpPost ( $wpPostId )
	{
		delete_post_meta( $wpPostId, 'fsp_cache_schedules_data' );
	}

	public static function restoreScheduleCacheDataForWpPost ( $wpPostId, $scheduleGroupId )
	{
		$schedulesCachedData = get_post_meta( $wpPostId, 'fsp_cache_schedules_data', true );

		if( ! empty( $schedulesCachedData ) )
		{
			self::createSchedulesFromWpPost( $wpPostId, $scheduleGroupId, $schedulesCachedData );
			self::deleteScheduleCacheDataForWpPost( $wpPostId );
		}
	}

	public static function deleteSchedulesFromWpPost ( $wpPostId, $scheduleGroupId )
	{
		Schedule::where( 'wp_post_id', $wpPostId )
		        ->where( 'group_id', $scheduleGroupId )
		        ->delete();
	}

    public static function shareQueuedSchedules ()
    {
        $all_blogs = Helper::getBlogs();

        foreach ( $all_blogs as $blog_id )
        {
            Helper::setBlogId( $blog_id );

            $wpPostSubQuery = Post::select('if(`post_status`=\'publish\' OR `post_type`=\'fsp_post\' OR `post_type`=\'attachment\', 1, 0)')
                ->where('ID', DB::field('wp_post_id'));

            $schedules = Schedule::where( 'status', 'not_sent' )
                ->where( 'send_time', '<=', Date::dateTimeSQL() )
                // ashagidaki subquerynin sebebi odur ki, feature statuslu wp postlari FS Poster daha tez goturub share edir
                // neticede postun linki slug ile yox /?p={id} formasinda dushur (wordpressde publish olmayan postlar uchun pretty link formati verilmir)
                // bele anladim ki, WP post statusunu cron job ile feature->publish edir. Ve bu cron job gec ishe dushur.
                // neticede FS Poster daha once ishe dushur ve postu paylashir social networkde ve link sehv yazilir.
                ->where($wpPostSubQuery, '1')
                ->limit( 15 )
                ->fetchAll();

            $schedules   = empty( $schedules ) ? [] : $schedules;
            $scheduleIds = [];

            foreach ( $schedules as $schedule )
            {
                $scheduleIds[] = $schedule->id;
            }

            if ( !empty( $scheduleIds ) )
            {
                Schedule::where( 'id', 'in', $scheduleIds )->update( [ 'status' => 'sending' ] );
				$uniqueWpPosts = [];
				foreach ( $schedules AS $schedule )
				{
					$wpPostId = $schedule->wp_post_id;

					if( isset( $uniqueWpPosts[$wpPostId] ) )
						continue;

					$uniqueWpPosts[$wpPostId] = true;
					$wpPost = get_post( $wpPostId );

					if( $wpPost->post_type !== 'fsp_post' )
						update_post_meta( $wpPostId, 'fsp_runned_for_this_post', true );
				}

                foreach ( $schedules as $schedule )
                {
                    self::shareSchedule( $schedule[ 'id' ], true );
                }

                $pendingPosts = Schedule::where( 'status', 'not_sent' )->where( 'send_time', '<=', Date::dateTimeSQL() )->count();

                if ( !empty( $pendingPosts ) )
                {
                    wp_remote_get( site_url() . '/wp-cron.php?doing_wp_cron', [ 'blocking' => false ] );
                }
            }

            Helper::resetBlogId();
        }
    }

    // doit $secureShare ancag true gelir. bu ne uchun yaradilib? gite baxmag lazimdi historye...
    public static function shareSchedule ( int $scheduleId, bool $secureShare = false ): void
    {
        $scheduleObj = new ScheduleObject( $scheduleId );

        if ( !$secureShare || $scheduleObj->getSchedule()->status === 'sending' )
        {
            $result = self::shareHelper( $scheduleObj );

            self::handleSchedules( $scheduleObj, $result );
        }

		unset( $scheduleObj );
    }

    private static function shareHelper ( ScheduleObject $scheduleObj )
    {
        try
        {
            $result = apply_filters( 'fsp_share_post', new ScheduleResponseObject(), $scheduleObj );
        } catch ( ChannelSessionException $e )
        {
            do_action( 'fsp_disable_channel', $scheduleObj->getSocialNetwork(), $scheduleObj->getChannel(), $scheduleObj->getChannelSession() );
            $resp            = new ScheduleResponseObject();
            $resp->status    = 'error';
            $resp->error_msg = fsp__( 'Social channel session has been expired' );
            return $resp;
        } catch ( ScheduleShareException $e )
        {
            $resp            = new ScheduleResponseObject();
            $resp->status    = 'error';
            $resp->error_msg = $e->getMessage();

            return $resp;
        } catch ( \Throwable $e )
        {
            $resp            = new ScheduleResponseObject();
            $resp->status    = 'error';
            $resp->error_msg = $e->getMessage();

            return $resp;
        }

        if ( !empty( $result ) )
            return $result;

        $postResponse            = new ScheduleResponseObject();
        $postResponse->status    = 'error';
        $postResponse->error_msg = fsp__( 'The account has been deleted. <a href="https://www.fs-poster.com/documentation/commonly-encountered-issues#issue13" target=\'_blank\'>Learn more!</a>' );

        return $postResponse;
    }

    private static function handleSchedules ( ScheduleObject $scheduleObj, ScheduleResponseObject $result )
    {
        $scheduleData = $scheduleObj->getSchedule()->data_obj->toArray();

        Schedule::where( 'id', $scheduleObj->getSchedule()->id )->update( [
            'send_time'      => Date::dateTimeSQL(),
            'status'         => $result->status,
            'error_msg'      => Helper::cutText( ( $result->error_msg ?? '' ), 797 ),
            'remote_post_id' => $result->remote_post_id ?? null,
            'data'           => json_encode( array_merge( $scheduleData, $result->data ) ),
        ] );
    }

}